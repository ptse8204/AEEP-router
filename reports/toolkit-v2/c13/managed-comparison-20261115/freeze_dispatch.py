"""Create the single executable review after the approved offline checks."""

import asyncio
import json
import runpy
import tempfile
from pathlib import Path

from dispatch_tasks import bind_tasks, task_pins
from prepare_renewal import snapshot
from prepare_runtime import (
    CONFIG,
    DESIGN,
    DESIGN_SHA256,
    DOCKER_PATH,
    ROOT,
    WORK,
    docker,
    read,
    require_reserve,
    sha,
    write,
)
from rebind_source import SOURCE_ROOT, STACK_REBINDING, derive
from run_dispatch import (
    APPROVAL,
    BASE,
    BUDGET,
    COLLECTOR,
    HERE,
    REVIEW,
    RUN,
    TRIAL,
    explicit_approval,
    proxy_state,
    render_result,
)

from aeep.assessment.models import AssessmentBudgetAmendment, AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore


def actual_workers():
    worker_root = WORK / "verified-worker-observations"
    images = read(WORK / "verified-image-bindings.json")
    result = {}
    for domain, pair in images.items():
        records = {}
        for role, image in pair.items():
            proof = worker_root / f"{domain}-{role}.json"
            if (domain, role) == ("document_data", "treatment"):
                proof = WORK / "candidate-granular-verification" / proof.name
            row = read(proof)
            assert row["image"] == image["id"] and row["passed"] and row["cleanup_confirmed"]
            assert row["auth_canary"] == {"result": "blocked"}
            assert row["collector"] == {"collector_connection_denied": True}
            assert row["sol_medium_catalogue"] and not row["model_turns"]
            assert docker("image", "inspect", "--format", "{{.Id}}", row["image"]) == row["image"]
            records[role] = row | {
                "observed_record_sha256": sha(proof),
                "observed_path": str(proof),
            }
        assert (
            records["control"]["runtime"]["shared_tools"]
            == records["treatment"]["runtime"]["shared_tools"]
        )
        assert pair["control"]["policy_sha256"] == pair["treatment"]["policy_sha256"]
        assert (
            records["control"]["effective_skill"] is None
            and records["treatment"]["effective_skill"]
        )
        result[domain] = records
    return result


async def draft():
    assert sha(DESIGN) == DESIGN_SHA256
    assert not REVIEW.exists() and not APPROVAL.exists() and not RUN.exists()
    design = read(DESIGN)
    source = verification_source_digest(SOURCE_ROOT)
    rebinding = read(STACK_REBINDING)
    assert source == rebinding["implementation_source"]
    assert design["stack_completion_ref"] == rebinding["original_completion_ref"]
    require_reserve()
    with ReceiptStore(BASE.parent / "aeep.sqlite3", read_only=True) as db:
        assert derive(AssessmentRepository(db), source) == rebinding
    pairs = actual_workers()
    grade_path = WORK / "protected-grader-verification.json"
    graders = read(grade_path)
    assert graders["passed"] and not graders["model_turns"] and len(graders["tasks"]) == 4
    assert all(len(grade["grade_controls"]) == 3 for grade in graders["tasks"].values())
    for name, digest in graders["receipts"].items():
        assert sha(WORK / "grader-receipts" / name) == digest
    renewal_file = WORK / "expiry-only-renewal.json"
    renewal_audit = WORK / "expiry-only-renewal-audit.json"
    renewal = AssessmentBudgetAmendment.model_validate(read(renewal_file))
    grant = read(renewal_audit)
    original, effective, counters, predecessor, reserved = snapshot()
    assert predecessor == renewal.previous_amendment_digest and effective.limits == renewal.limits
    assert content_digest(original) == renewal.authorization_digest
    assert content_digest(renewal) == grant["canonical_amendment_digest"]
    assert content_digest(reserved) == grant["prior_reservations_sha256"]
    assert list(counters[1:]) == grant["unchanged_counters"]
    assert not grant["operational_ledger_amended"] and grant["copied_ledger_validated"]
    proxy = proxy_state(design["worker_inputs"]["proxy_id"])
    assert proxy["Image"] == design["worker_inputs"]["proxy_image_id"] and not proxy["Running"]
    assert set(proxy["Networks"]) == {"aeep-reviewed-model-private", "aeep-reviewed-model-egress"}
    tasks = await task_pins()
    assert tasks == await task_pins()
    envelope = {
        "maximum_model_turns": 8,
        "maximum_operations": 48,
        "maximum_reserved_seconds": 6800,
        "proxy_session_wall_timeout_seconds": 5700,
        "single_turn_seconds": 300,
        "maximum_cash_usd": "0",
    }
    # Eight worker inspections, eight task turns, eight verifier calls, one
    # preflight router and two trial routers per case, four reports and one proxy.
    grade_bound = sum(
        (entry[1].extension.grader.config["timeout_seconds"] + 5) * 2 for entry in bind_tasks()
    )
    calculated = 8 * 240 + 8 * 305 + grade_bound + 12 * 30 + 4 * 30 + 120
    assert (
        calculated
        <= envelope["maximum_reserved_seconds"]
        <= design["maximum_live_scope"][
            "seconds_reserved_including_readiness_grading_and_reporting"
        ]
    )
    assert (
        41
        <= envelope["maximum_operations"]
        <= design["maximum_live_scope"]["operations_including_readiness_grading_and_reporting"]
    )
    budget = runpy.run_path(str(BUDGET))
    guards = budget["self_check"]()
    total = AssessmentLimits(max_model_turns=8, max_operations=48, max_elapsed_seconds=6800)
    budget["require_room"](counters[1:], counters[1:], total, envelope)
    assert effective.limits.max_model_turns - counters[2] >= 8
    assert effective.limits.max_operations - counters[1] >= 48
    assert effective.limits.max_elapsed_seconds - counters[3] >= 6800
    with tempfile.TemporaryDirectory(prefix="dispatch-report-check-", dir=WORK) as directory:
        render_result({"review_sha256": DESIGN_SHA256, "tasks": []}, Path(directory))
        assert "0/4" in (Path(directory) / "report.md").read_text()
        assert "0/4" in (Path(directory) / "report.html").read_text()

    gate_path = WORK / "dispatch-gate-verification.json"
    gates = read(gate_path)
    assert gates["real_pair_authorizations_followed_by_synthetic_probe_failure"] == 4
    assert gates["missing_evidence_rejections"] == 6
    assert gates["production_grant_and_reservations_unchanged"]
    assert not gates["proxy_starts"] and not gates["provider_requests"]
    pin_paths = {
        gate_path,
        STACK_REBINDING,
        BASE,
        DESIGN,
        Path(DOCKER_PATH),
        (CONFIG / "config.json").resolve(),
        BUDGET,
        TRIAL,
        COLLECTOR,
        grade_path,
        renewal_file,
        renewal_audit,
        WORK / "verified-image-bindings.json",
    }
    pin_paths.update(path for path in HERE.glob("*.py"))
    pin_paths.update(Path(row["observed_path"]) for pair in pairs.values() for row in pair.values())
    pin_paths.update(WORK / "grader-receipts" / name for name in graders["receipts"])
    for task in design["tasks_in_execution_order"]:
        for field in ("rights_review", "rights_record", "public_archive"):
            if "path" in task.get(field, {}):
                path = ROOT / task[field]["path"]
                assert sha(path) == task[field]["sha256"]
                pin_paths.add(path)
    image_list = {row["image"] for pair in pairs.values() for row in pair.values()}
    image_list.update(row["grader_image"] for row in graders["tasks"].values())
    review = {
        "schema_version": "aeep.operator.managed-sol-development-dispatch.v1",
        "design_sha256": DESIGN_SHA256,
        "implementation_source": source,
        "stack_completion_ref": rebinding["stack_completion_ref"],
        "original_stack_completion_ref": design["stack_completion_ref"],
        "frozen_source": str(SOURCE_ROOT),
        "approval_pending": True,
        "model": design["model"],
        "reasoning_effort": design["reasoning_effort"],
        "tasks": tasks,
        "paired_order": design["pair_order_by_task"],
        "worker_images": sorted(image_list),
        "worker_offline_receipts": pairs,
        "protected_grader_verification": {"path": str(grade_path), "sha256": sha(grade_path)},
        "proxy": proxy,
        "grant": grant,
        **envelope,
        "calculated_operation_reservations": 41,
        "calculated_reserved_seconds": calculated,
        "automatic_retries": 0,
        "model_fallback": False,
        "public_input_scope": design["tasks_in_execution_order"],
        "disclosure": "Only bound public instructions, archives and the cleared optional candidate "
        "instructions used by managed GPT-6.1 Sol through the existing Codex proxy. "
        "The private installed Spreadsheets runtime remains local. License terms are unasserted in its "
        "runtime package metadata. Approval covers private operator evaluation in the existing environment.",
        "remaining_pre_dispatch_checks": [
            "Revalidate the files and frozen source. Register the 37 independently revalidated checks "
            "under the clean source fingerprint using the exact copied-ledger binding. Preserve the prior completion.",
            "Apply the exact expiry-only amendment; preserve both outstanding older reservations and all counters.",
            "Start only the retained proxy. Before any model turn, complete fresh authenticated probes for "
            "all four task bindings, match GPT-6.1 Sol medium, and verify collector denial and cleanup.",
        ],
        "report_scope": "Protected task scores, all verified raw token fields, paired differences and timings, "
        "operation ledgers, and evidence gaps. Four exposed development tasks. No formal qualification or selection claim.",
        "stop_conditions": design["stop_conditions"],
        "pins": {str(path): sha(path) for path in sorted(pin_paths)},
        "preflight": {
            "budget_guards_passed": guards,
            "local_dispatch_gate_verification": gates,
            "distinct_task_prompt_pairs": 4,
            "deterministic_rebuild": True,
            "new_external_requests": 0,
            "dispatches": 0,
        },
        "execution": [
            "/usr/bin/env",
            "PYTHONPATH=" + str(SOURCE_ROOT / "src"),
            "python3",
            "-B",
            str(HERE / "run_dispatch.py"),
            "--execute-approved",
            "<review-sha256>",
        ],
    }
    write(REVIEW, review)
    try:
        explicit_approval(sha(REVIEW))
    except RuntimeError:
        print(
            json.dumps(
                {
                    "review_sha256": sha(REVIEW),
                    "approval_missing_blocks_dispatch": True,
                    "calculated_reserved_seconds": calculated,
                    **envelope,
                },
                indent=2,
            )
        )
    else:
        raise AssertionError("unapproved review accepted")


if __name__ == "__main__":
    asyncio.run(draft())
