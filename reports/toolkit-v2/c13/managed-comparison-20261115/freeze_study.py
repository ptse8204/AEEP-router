"""Freeze the comparison design from retained artifacts without dispatching work."""

import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import require_stack_complete

HERE = Path(__file__).resolve().parent
C13 = HERE.parent
ROOT = HERE.parents[3]
LOCAL = ROOT / ".aeep"
DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
DATABASE = Path("/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3")


def read(path):
    return json.loads(path.read_bytes())


def bind(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "sha256": digest,
    }


def public_archive(encoded, expected):
    contents = base64.b64decode(encoded, validate=True)
    assert hashlib.sha256(contents).hexdigest() == expected
    return {"sha256": expected, "bytes": len(contents)}


def host_config(pair):
    return read(pair)["control"]["config"]["managed_worker"]


def docs():
    sales = C13 / "skillsbench-sales-handoff-20261105"
    excel = C13 / "skillsbench-document-managed-20261106"
    disclosure = C13 / "skillsbench-task-disclosure-20261105/operation-review.json"
    excel_rights = C13 / "skillsbench-document-rights-20261106/operation-review.json"
    bindings = [
        (
            LOCAL / "skillsbench-sales-handoff-20261105/sales-prepared/plan.json",
            read(disclosure)["records"][0]["eligible_for_separate_dispatch_review"],
            disclosure,
            sales / "operation-review.json",
            read(sales / "operation-review.json")["cases"][0]["grader_image_id"],
        ),
        (
            LOCAL
            / "skillsbench-document-managed-20261106/managed-execution/excel-prepared/plan.json",
            next(
                row for row in read(excel_rights)["tasks"] if row["task_id"] == "exceltable-in-ppt"
            )["public_files"],
            excel_rights,
            excel / "packaged-grading/grader-review.json",
            (LOCAL / "skillsbench-document-managed-20261106/excel-image-id").read_text().strip(),
        ),
    ]
    tasks = []
    for plan_file, public_files, rights, grader_review, grader_image in bindings:
        plan = read(plan_file)
        [case] = plan["suite"]["cases"]
        value = case["action"]["input"]
        tasks.append(
            {
                "id": case["case_id"],
                "domain": "document-data",
                "revision": "9a1f4dd5f7659f75707435da3ce854b6e48321d1",
                "public_archive": public_archive(
                    value["task_archive_b64"], value["task_archive_sha256"]
                ),
                "public_files": public_files,
                "task_input_digest": content_digest(value),
                "rights_review": bind(rights),
                "protected_grader": {
                    "image": grader_image,
                    "historical_review": bind(grader_review),
                    "historical_recipe_digest": plan["recipe_digest"],
                    "original_validator_binding": content_digest(case["validators"]),
                },
            }
        )
    assert [task["id"] for task in tasks] == ["sales-pivot-analysis", "exceltable-in-ppt"]
    return tasks


def software():
    directory = C13 / "repository-usefulness-pilot-20261029"
    cohort_file, recipe_file = (directory / name for name in ("cohort.json", "recipe.json"))
    cases = {row["task_id"]: row for row in read(cohort_file)["cases"]}
    protected = {
        row["input"]["task_id"]: row for row in read(recipe_file)["generator_config"]["cases"]
    }
    tasks = []
    for identity in (
        "canopen-python__canopen-613-declared-tests",
        "tefra__xsdata-1126-issue-behavior-audit",
    ):
        case, grader = cases[identity], protected[identity]
        archive = Path(case["public_archive"]["path"])
        assert bind(archive)["sha256"] == case["public_archive"]["sha256"]
        assert archive.stat().st_size == case["public_archive"]["size_bytes"]
        grader_image = case["historical_runtime_binding"]["image_id"]
        tasks.append(
            {
                "id": identity,
                "domain": "software-engineering",
                "origin": case["origin_kind"],
                "repository": case["repository"],
                "revision": case["revision"],
                "public_archive": bind(archive) | {"bytes": archive.stat().st_size},
                "task_input_digest": content_digest(grader["input"]),
                "rights_record": bind(cohort_file),
                "protected_grader": {
                    "image": grader_image,
                    "historical_recipe": bind(recipe_file),
                    "binding": content_digest(grader["truth"]),
                    "reference_digest": grader["reference"]["sha256"],
                    "required_test_identities": case["required_identities"],
                },
            }
        )
    return tasks


def study():
    completion = read(HERE / "operational-completion.json")
    source = verification_source_digest(ROOT)
    assert source == completion["implementation_source"]
    with ReceiptStore(DATABASE, read_only=True) as store:
        repo = AssessmentRepository(store)
        require_stack_complete(repo, completion["stack_completion_ref"], source_digest=source)
        grant = repo.effective_grant("onboarding")
        counters = list(
            store._connection.execute(
                "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants "
                "WHERE id='onboarding' AND revoked=0"
            ).fetchone()
        )
        predecessor = store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='budget_amendment' "
            "AND json_extract(payload_json,'$.authorization_id')='onboarding' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0]
        reservations = store._connection.execute(
            "SELECT count(*) FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'"
        ).fetchone()[0]

    sol = LOCAL / "skillsbench-react-managed-preparation-20261107"
    sol_pair = sol / "sol-permitted-path-live-definitions/react-pair.json"
    sol_config = host_config(sol_pair)
    binary = sol / "sol-client-context/runtime/bin/codex"
    assert bind(binary)["sha256"] == sol_config["binary_sha256"]
    prior_sol = (
        C13
        / "skillsbench-react-managed-preparation-20261107/sol-permitted-path-live-20261109/operation-review.json"
    )
    proxy = read(prior_sol)["proxy"]
    sales = LOCAL / "skillsbench-managed-worker-preparation-20261105/engineering/sales-pair.json"
    excel = LOCAL / "skillsbench-document-managed-20261106/worker-definitions/excel-pair.json"
    assert host_config(sales)["image"] == host_config(excel)["image"]
    doc_base = host_config(sales)["image"]
    legacy = ROOT / "reports/v08/sol-workbook-qualification-profile-review-bundle.json"
    old_pair = read(legacy)["definitions"][
        "471fa980fd9ffe84638ebc428e7ac5602e6197f55db6c4d520b650dd6fb9dbf4"
    ]
    spreadsheet = old_pair["treatment"]["config"]["managed_worker"]["image"]
    specialist = C13 / "stack-delivery-20261030"
    wheels = [
        asset
        for asset in read(specialist / "candidate-preparation.json")["selected_wheels"]
        if not asset["filename"].startswith("ruff")
    ]
    for wheel in wheels:
        archive = LOCAL / "stack-candidate-review-20261030" / wheel["filename"]
        assert (
            bind(archive)["sha256"] == wheel["sha256"] and archive.stat().st_size == wheel["bytes"]
        )
    tasks = docs() + software()
    images = sorted(
        {
            doc_base,
            spreadsheet,
            sol_config["image"],
            *(task["protected_grader"]["image"] for task in tasks),
        }
    )
    for image in images:
        observed = subprocess.check_output(
            [DOCKER, "image", "inspect", "--format", "{{.Id}}", image], text=True, timeout=15
        ).strip()
        assert observed == image
    observed_proxy = subprocess.check_output(
        [DOCKER, "inspect", "--format", "{{.Id}} {{.Image}} {{.State.Running}}", proxy["Id"]],
        text=True,
        timeout=15,
    ).split()
    assert observed_proxy == [proxy["Id"], proxy["Image"], "false"]
    free = shutil.disk_usage(ROOT).free
    assert free >= 50 * 1024**3
    return {
        "schema_version": "aeep.operator.managed-comparison-design.v1",
        "status": "DESIGN_REVIEW_ONLY",
        "dispatch_authorized": False,
        "implementation_source": source,
        "stack_completion_ref": completion["stack_completion_ref"],
        "question": "Does optional access to a relevant capability change protected task success, "
        "token usage, or time on either development workload?",
        "evaluator": "Existing AEEP AssessmentService and BenchmarkRunner with managed Codex",
        "development_path": "Reuse the bounded development schedule and canonical receipt/report flow. "
        "The formal managed workflow requires matched qualification and its existing frozen cohorts. "
        "Do not reclassify the engineering recipes or exposed tasks as formal holdout.",
        "model": "gpt-6.1-sol",
        "reasoning_effort": "medium",
        "fallback": False,
        "candidate_arms": {
            "baseline": "Capable ordinary task tools, same model and instruction, no added candidate.",
            "document-data": {
                "optional_candidate": "Spreadsheets 26.915.20218 as retained in the exact image",
                "source_image": spreadsheet,
                "skill_sha256": old_pair["candidate_skill_digest"],
                "historical_pair_definition": bind(legacy),
                "candidate_runtime_copy_requires_license_and_boundaries_review": True,
            },
            "software-engineering": {
                "optional_candidate": "LibCST 1.8.6 through the retained libcst-migrate skill",
                "candidate_skill": bind(
                    ROOT / "examples/toolkit_repository_specialists/libcst-migrate/SKILL.md"
                ),
                "local_wheels": wheels,
                "parked_runtime_review": bind(
                    specialist / "launcher-correction/specialist-runtime-review.json"
                ),
                "fresh_build_and_functional_checks_required": True,
            },
        },
        "worker_inputs": {
            "document_baseline_parent": doc_base,
            "document_parent_bindings": [bind(sales), bind(excel)],
            "software_baseline_parent": sol_config["image"],
            "sol_binary": bind(binary),
            "sol_path": sol_config["binary"],
            "sol_runtime_inventory": bind(sol / "sol-client-context-inventory.json"),
            "prior_sol_dispatch_review": bind(prior_sol),
            "proxy_id": proxy["Id"],
            "proxy_image_id": proxy["Image"],
            "retained_images_verified": images,
            "final_pair_and_collector_refs": None,
        },
        "tasks_in_execution_order": tasks,
        "pair_order_by_task": [
            "baseline/treatment",
            "treatment/baseline",
            "baseline/treatment",
            "treatment/baseline",
        ],
        "analysis": {
            "tier": "Exposed development tasks. Report paired observations by task and by domain.",
            "primary": "Original protected 0/1 task score and matched difference.",
            "secondary": "Matched provider input, cached input, cache-write, output, and "
            "reasoning token fields when present; wall time; operation costs; failure and measurement coverage.",
            "candidate_use": "Record listed, retrieved and invoked separately where evidenced. "
            "Unknown utilization stays unknown.",
            "repetitions": 1,
            "formal_hypothesis_or_selection_claim": False,
        },
        "maximum_live_scope": {
            "model_turn_reservations": 8,
            "operations_including_readiness_grading_and_reporting": 640,
            "seconds_reserved_including_readiness_grading_and_reporting": 32000,
            "single_model_turn_timeout_seconds": 300,
            "reservation_basis": "At most 80 operations and 4,000 seconds per trial-equivalent, "
            "including setup and verification. Derive the actual upper allowance from the exact "
            "schedule before requesting live approval.",
            "cash_usd": "0",
            "automatic_retries": 0,
            "minimum_host_free_bytes": 50 * 1024**3,
        },
        "grant_readback": {
            "authorization_id": "onboarding",
            "current_counters": counters,
            "current_limits": grant.limits.model_dump(mode="json"),
            "expires_at": grant.expires_at.isoformat(),
            "expired_at_plan_preparation": grant.expires_at <= utc_now(),
            "previous_budget_amendment": predecessor,
            "prior_reservations_preserved": reservations,
        },
        "disclosure_limit": "The four bound public tasks and their exact permitted inputs, editable "
        "paths, output contracts, and reviewed candidate instructions as used, through the existing "
        "managed Codex proxy only. Protected tests and reference outputs stay in the offline grader. "
        "No new service, credential access, cash spending, fallback, publication or release.",
        "prerequisites_for_dispatch_proposal": [
            "Freeze actual additive worker image IDs, shared tool parity, candidate bytes/rights, "
            "source-bound isolation and collector receipts, and repository public archive wiring.",
            "Retain genuine protected grades for reference, failure controls and error handling under "
            "the exact current carrier. Keep historical engineering plans at their original scope.",
            "Exercise the bounded development schedule with local substitutes. Freeze canonical "
            "assessment and operation reviews and confirm they fit the existing grant with an expiry-only amendment.",
            "Obtain separate explicit operator approval of the complete live review before any provider contact.",
        ],
        "stop_conditions": [
            "Any source, image, task, grader, model, destination, permission, inventory, budget or authority drift.",
            "Any denied isolation probe, unavailable exact model, unsettled relevant attempt, or inadequate disk reserve.",
            "Any indeterminate trial, missing required grade or token-capture evidence, accounting mismatch or uncertain cleanup. "
            "Retain successful settlement and genuine zero-score task outcomes. Reconcile an incomplete run read-only.",
        ],
        "live_review_sha256": None,
        "plan_preparation": {"worker_starts": 0, "model_calls": 0, "host_free_bytes": free},
    }


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, allow_nan=False))
