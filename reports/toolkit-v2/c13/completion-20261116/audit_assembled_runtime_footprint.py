"""Measure retained images and reconcile accepted workflow overhead read-only."""

import json
import re
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from check_linux_install import HERE, ROOT, SOCKET, get
from measure_retained_footprint import REBIND

from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentPlan,
    AssessmentReport,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkCampaignReport
from aeep.hosts.workers import ManagedWorkerBinding
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.stack_readiness import _resolve
from aeep_toolkit.workflow_evidence import _settled
from aeep_toolkit.workflow_telemetry import campaign_receipt

BASELINE = HERE / "retained-runtime-footprint.json"
LEDGER = ROOT.parent / "aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3"
WORKFLOWS = ("workflow-document-data", "workflow-software-engineering")
REPORT_COMPONENTS = (*WORKFLOWS, "agent-skill-eval", "aeep-evaluator", "skillrank")


def engine(path):
    """Read one local Engine endpoint without persisting unrelated metadata."""
    return json.loads(subprocess.check_output(
        ["/usr/bin/curl", "-q", "--unix-socket", SOCKET, "--max-time", "45", "--max-filesize",
         "16777216", "-fsS", "http://localhost" + path],
        stdin=subprocess.DEVNULL, env={}, timeout=50,
    ))


def checked_id(value):
    if not isinstance(value, str) or re.fullmatch("sha256:[0-9a-f]{64}", value) is None:
        raise ValueError("expected an exact Docker image or layer identity")
    return value


def accepted_plans(repo, packet):
    plans, overhead = {}, {}
    for component in REPORT_COMPONENTS:
        record = packet["records"][component]["value"]
        reference = packet["completion"]["components"][component]
        if content_digest(record) != reference:
            raise ValueError("retained readiness record differs")
        if component in WORKFLOWS:
            accepted = record["observations"]
            report_ref = accepted["report_ref"]
        else:
            proof = record["proof"]
            report_ref = proof["diagnostic_report_ref" if component == "skillrank" else "report_ref"]
        report = _resolve(repo, "report", report_ref, AssessmentReport)
        plan = _resolve(repo, "plan", report.plan_digest, AssessmentPlan)
        environment = _resolve(repo, "environment", plan.environment_digest, AssessmentEnvironment)
        campaign = _resolve(repo, "campaign", report.campaign_digest, BenchmarkCampaignReport)
        request = RecipeMaterializationRequest(
            **{key: getattr(plan, key) for key in (
                "subject_digest", "recipe_digest", "mapping_digest", "environment_digest",
                "authorization_id", "definition_digests",
            )},
            seed=0,
        )
        workers = {}
        for arm in (plan.comparison.baseline, plan.comparison.candidate):
            worker = ManagedWorkerBinding.model_validate(arm.host_config["managed_worker"])
            proofs = []
            for trial in campaign.trials:
                if trial.route_id != arm.executor_id:
                    continue
                for receipt_id in trial.receipt_ids:
                    receipt = campaign_receipt(repo, report_ref, receipt_id, plan, request)
                    if receipt.metadata.get("worker_digest") != worker.digest():
                        raise ValueError("worker receipt does not match its frozen plan")
                    proofs.append(content_digest(receipt))
            workers[arm.executor_id] = {"image": checked_id(worker.image), "observed_receipts": proofs}
        plans[component] = {
            "report_ref": report_ref,
            "plan_ref": report.plan_digest,
            "grading_image": checked_id(environment.container_image),
            "workers": workers,
        }
        if component in WORKFLOWS:
            if accepted["plan_ref"] != report.plan_digest:
                raise ValueError("workflow evidence points to another plan")
            account = accepted["workflow_accounting"]
            charge = _settled(repo, account["operation_id"])
            if (
                plan.plan_id not in account["assessment_plan_ids"]
                or charge.elapsed_seconds is None or charge.resources is None
                or charge.stage != "workflow_run_overhead"
            ):
                raise ValueError("exclusive wrapper overhead is missing")
            overhead[component] = {
                "charged_operation_ref": content_digest(charge),
                "wrapper_exclusive_wall_seconds": charge.elapsed_seconds,
                "wrapper_process_cpu_ms": charge.resources.cpu_ms,
                "accepted_trial_count": len(accepted["trials"]),
                "agent_wall_seconds_sum_if_all_known": known_sum(accepted["trials"], "agent_wall_seconds"),
                "protected_grading_wall_seconds_sum_if_all_known": known_sum(
                    accepted["trials"], "verification_wall_seconds"
                ),
            }
    return plans, overhead


def known_sum(rows, key):
    if not rows or any(row.get(key) is None for row in rows):
        return None
    return sum(row[key] for row in rows)


def aligned_chains(layers, sizes_newest_first):
    """Build one ID per unpacked filesystem chain after a complete history join."""
    if any(type(value) is not int or value < 0 for value in sizes_newest_first):
        raise ValueError("invalid engine history size")
    sizes = [value for value in reversed(sizes_newest_first) if value]
    if not layers or len(layers) != len(sizes):
        return None
    parent = ""
    chains = {}
    for layer, size in zip(layers, sizes, strict=True):
        parent = content_digest({"parent": parent, "diff": checked_id(layer)})
        chains[parent] = size
    return chains


def image_chains(image):
    inspect = engine("/images/" + image + "/json")
    if inspect["Id"] != image:
        raise ValueError("selected image changed during inspection")
    history = engine("/images/" + image + "/history")
    return aligned_chains(inspect["RootFS"]["Layers"], [item["Size"] for item in history])


def layer_union(by_image):
    merged = {}
    for chains in by_image.values():
        if chains is None:
            continue
        for identity, size in chains.items():
            if merged.setdefault(identity, size) != size:
                raise ValueError("shared layer reports inconsistent history sizes")
    return merged


def image_and_volume_usage(images, volume_names):
    usage = engine("/system/df?type=image")["Images"]
    subset = {row["Id"]: row for row in usage if row["Id"] in images}
    with ThreadPoolExecutor(max_workers=4) as pool:
        chains = dict(zip(subset, pool.map(image_chains, subset), strict=True))
    totals = layer_union(chains)
    per_image = {}
    for image, participants in sorted(images.items()):
        entry = subset.get(image)
        row = {"selected_roles": sorted(participants), "engine_summary_present": entry is not None}
        if entry is not None:
            size, shared = entry["Size"], entry["SharedSize"]
            if type(size) is not int or type(shared) is not int or size < 0 or not -1 <= shared <= size:
                raise ValueError("invalid image size in daemon snapshot")
            row.update(
                engine_size_bytes=size,
                engine_shared_bytes=shared if shared >= 0 else None,
                container_reference_count=entry["Containers"],
                unpacked_history_bytes=sum(chains[image].values()) if chains[image] is not None else None,
            )
        per_image[image] = row
    volumes = dict.fromkeys(sorted(volume_names))
    for entry in engine("/system/df?type=volume")["Volumes"]:
        if entry["Name"] in volumes:
            usage = entry.get("UsageData") or {}
            if type(size := usage.get("Size")) is int and size >= 0:
                volumes[entry["Name"]] = {"engine_size_bytes": size, "references": usage["RefCount"]}
    return {
        "configured_image_count": len(per_image),
        "measured_image_count": len(subset),
        "unpacked_history_matched_image_count": sum(value is not None for value in chains.values()),
        "deduplicated_matched_history_bytes": sum(totals.values()),
        "matched_unpacked_chain_count": len(totals),
        "engine_gross_selected_image_bytes": sum(row["Size"] for row in subset.values()),
        "engine_per_image_unique_bytes_if_all_known": known_sum(
            [{"unique": row["Size"] - row["SharedSize"] if row["SharedSize"] >= 0 else None}
             for row in subset.values()], "unique",
        ) if subset.keys() == images.keys() else None,
        "images": per_image,
        "langfuse_volumes": volumes,
        "engine_langfuse_volume_bytes_if_all_known": known_sum(
            [value or {} for value in volumes.values()], "engine_size_bytes"
        ),
    }


def audit():
    retained = get(BASELINE)
    packet = get(REBIND)
    current = get(HERE / "current-stack-source-binding.json")
    if (
        packet["stack_completion_ref"] != retained["observed_stack_completion_ref"]
        or packet["stack_completion_ref"] != current["original_completion_ref"]
        or current["accepted_checks"] != 37
    ):
        raise ValueError("retained footprint and current stack are unrelated")
    images = defaultdict(set, {
        checked_id(image): set(details["components"])
        for image, details in retained["images"].items()
    })
    with ReceiptStore(LEDGER, read_only=True) as store:
        plans, overhead = accepted_plans(AssessmentRepository(store), packet)
    for component, record in plans.items():
        images[record["grading_image"]].add(component + "/protected-grader")
        for label, worker in record["workers"].items():
            images[worker["image"]].add(component + "/" + label)
    volumes = set(retained["langfuse_project_volume_measurements_as_printed"])
    if len(volumes) != retained["langfuse_project_volume_count"]:
        raise ValueError("retained volume scope is incomplete")
    choices = image_and_volume_usage(images, volumes)
    return {
        "schema_version": "aeep.c13.assembled-runtime-footprint.v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "proof_sha256": {path.name: file_digest(path) for path in (
            BASELINE, REBIND, HERE / "current-stack-source-binding.json"
        )},
        "source_digest": current["implementation_source"],
        "current_stack_completion_ref": current["copied_completion_ref"],
        "previous_image_count": retained["identified_image_count"],
        "engine_api": engine("/version")["ApiVersion"],
        "accepted_plan_runtime_bindings": plans,
        "accepted_wrapper_overhead": overhead,
        **choices,
        "resources_started_or_removed": 0,
        "new_task_runs": 0,
        "scope": [
            "Selected retained Docker images, reviewed plan worker pairs and named Langfuse volumes.",
            "Daemon size and unpacked image history have different accounting definitions.",
            "Deduplicated history counts verified filesystem chains once. Ambiguous joins remain unknown.",
            "Host allocation, reclaimable host space, native runtimes, temporary files and maintenance labor are outside this measurement."
        ],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
