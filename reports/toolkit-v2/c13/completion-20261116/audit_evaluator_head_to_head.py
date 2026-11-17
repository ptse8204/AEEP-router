"""Reconcile the real Markdownify engine runs and earlier ordinary Codex control."""

import argparse
import json
import socket
from pathlib import Path
from unittest.mock import patch

from check_linux_install import HERE, get

from aeep.assessment.models import (
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentReport,
    AssessmentRunBinding,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkCampaignReport
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.stack_readiness import _resolve
from aeep_toolkit.stack_receipts import StackReceiptEvidence, verify_receipt_evidence
from aeep_toolkit.telemetry import token_capture
from aeep_toolkit.workflow_evidence import _settled
from aeep_toolkit.workflow_telemetry import campaign_receipt_and_journal

ENGINE_RUNS = HERE.parent / "integration-snapshot-correction-20261103"
CONTROL = HERE.parent / "repository-usefulness-plain-20261029"
TASK = "matthewwithanm__python-markdownify-200"
RETAINED = HERE.parent / "managed-comparison-20261115/offline-evidence/source-stack-rebinding.json"
TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
HOST_KEYS = (
    "actual_model",
    "worker_digest",
    "host_runtime_digest",
    "boundary_digest",
    "protocol_version",
    "host_advertised_inventory_digest",
    "candidate_skill_sha256",
    "task_instruction_sha256",
)


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def settled_row(repo, report_id, source, trial_id, receipt_ref, label):
    report = AssessmentReport.model_validate(repo.get("report", report_id))
    report_ref = content_digest(report)
    plan = _resolve(repo, "plan", report.plan_digest, AssessmentPlan)
    binding = AssessmentRunBinding.model_validate(repo.get("run_binding", plan.plan_id))
    campaign = _resolve(repo, "campaign", report.campaign_digest, BenchmarkCampaignReport)
    expected_ledger = _resolve(
        repo, "operation_ledger", report.operation_ledger_digest, AssessmentOperationLedger
    )
    (trial,) = [item for item in campaign.trials if item.trial_id == trial_id]
    (case,) = [item for item in plan.suite.cases if item.case_id == trial.case_id]
    (verifier,) = trial.case_validation
    (receipt_id,) = trial.receipt_ids
    charge = _settled(repo, trial.trial_id)
    request = RecipeMaterializationRequest(
        **{
            key: getattr(plan, key)
            for key in (
                "subject_digest",
                "recipe_digest",
                "mapping_digest",
                "environment_digest",
                "authorization_id",
                "definition_digests",
            )
        },
        seed=0,
    )
    receipt, journal = campaign_receipt_and_journal(repo, report_ref, receipt_id, plan, request)
    capture = token_capture(receipt, journal)
    require(
        report.report_id == report_id
        and plan.plan_id == expected_ledger.plan_id == binding.plan_id == charge.plan_id
        and binding.source_digest == source
        and case.case_id.removeprefix("development-") == TASK
        and trial.route_fingerprint == plan.route_fingerprints[trial.route_id]
        and trial.status == "success"
        and trial.retry_fallback_count == 0
        and trial.failure_category is None
        and trial.valid is True
        and verifier.kind == "callback"
        and verifier.trust == "verified"
        and verifier.valid is True
        and verifier.quality_score == 1
        and receipt.execution_success is True
        and content_digest(receipt) == receipt_ref
        and receipt.metadata.get("worker_cleanup_confirmed") is True
        and charge.stage == "trial"
        and charge.reserved.max_model_turns == 1
        and charge in expected_ledger.operations
        and capture["status"] == "verified"
        and set(capture["known_fields"]) == set(TOKEN_KEYS),
        "retained task grade, receipt, token or trial accounting differs",
    )
    tokens = {key: getattr(receipt.actual_resources, key) for key in TOKEN_KEYS}
    totals = tokens["input_tokens"] + tokens["output_tokens"]
    require(
        trial.wall_time_ms is not None and trial.grading_wall_time_ms is not None,
        "retained timing source is missing",
    )
    row = {
        "label": label,
        "task_id": TASK,
        "route_id": trial.route_id,
        "route_fingerprint": trial.route_fingerprint,
        "receipt_ref": receipt_ref,
        "report_ref": report_ref,
        "source": source,
        "trial_ref": content_digest(trial),
        "journal_ref": capture["journal_ref"],
        "task_input_sha256": content_digest(case.action.input),
        "protected_validator_sha256": content_digest(
            {"validators": [v.model_dump(mode="json") for v in case.validators]}
        ),
        **{key: receipt.metadata.get(key) for key in HOST_KEYS},
        "grade": 1,
        "score_scale": "binary",
        "retries": trial.retry_fallback_count,
        "provider_tokens": tokens,
        "reported_input_plus_output": totals,
        "agent_wall_seconds": trial.wall_time_ms / 1000,
        "protected_grading_seconds": trial.grading_wall_time_ms / 1000,
        "trial_charge_ref": content_digest(charge),
        "trial_reserved_models": charge.reserved.max_model_turns,
        "cash_measurement_status": receipt.accounting.cash.status.value,
        "task_artifacts_retained_by_audit": False,
    }
    return row, plan, case


def audit(repo):
    frozen = get(RETAINED)
    source = frozen["implementation_source"]
    checks = "agent-skill-eval", "aeep-evaluator"
    for component in checks:
        ref = frozen["completion"]["components"][component]
        record = _resolve(
            repo, "toolkit_stack_receipt_evidence", ref, StackReceiptEvidence, reviewed=True
        )
        require(
            dict(verify_receipt_evidence(repo, record, component=component, source=source)),
            "required retained engine proof is missing",
        )

    old = get(ENGINE_RUNS / "completion-audit.json")
    ase, managed = [
        settled_row(
            repo,
            row["canonical_report_id"],
            old["source"],
            row["trial_id"],
            row["receipt_ref"],
            row["engine"],
        )
        for row in old["rows"]
    ]
    a, plan_a, case_a = ase
    m, plan_m, case_m = managed
    require(
        a["label"] == "agent-skill-eval"
        and m["label"] == "managed"
        and plan_a.scheduler_digest is not None
        and plan_m.scheduler_digest is None,
        "engine attribution differs",
    )
    normal_a, normal_m = [repo.get("recipe", plan.recipe_digest) for plan in (plan_a, plan_m)]
    for recipe in (normal_a, normal_m):
        recipe.pop("recipe_id")
        recipe.pop("description")
        recipe["extension"].pop("template_families")
    require(
        normal_a == normal_m
        and case_a.validators == case_m.validators
        and case_a.action.model_dump(exclude={"action_id"})
        == case_m.action.model_dump(exclude={"action_id"}),
        "the engine reports differ beyond task or recipe labeling",
    )
    environments = [repo.get("environment", plan.environment_digest) for plan in (plan_a, plan_m)]
    for plan, envelope in zip((plan_a, plan_m), environments, strict=True):
        require(content_digest(envelope) == plan.environment_digest, "environment record changed")
        envelope.pop("environment_id")
    require(environments[0] == environments[1], "engine environments differ beyond their identity")
    keys = ("task_input_sha256", "protected_validator_sha256", "route_fingerprint", *HOST_KEYS)
    require(
        all(a[key] is not None and a[key] == m[key] for key in keys),
        "matched engine configuration or observed prompt differs",
    )

    control = get(CONTROL / "model-result.json")
    (found,) = [
        item
        for item in get(CONTROL / "completion-audit.json")["rows"]
        if item["case"] == TASK and item["arm"] == "control"
    ]
    n, plan_n, case_n = settled_row(
        repo,
        control["report_id"],
        control["source_digest"],
        found["trial_id"],
        found["receipt_ref"],
        "ordinary-codex",
    )
    require(
        plan_n.baseline_id == n["route_id"]
        and case_n.action.input == case_a.action.input
        and case_n.validators == case_a.validators,
        "ordinary Codex retained control is outside the Markdownify task",
    )
    native_differences = [key for key in keys if n[key] != a[key]]
    require(
        "task_instruction_sha256" in native_differences and "worker_digest" in native_differences,
        "ordinary contrast no longer has its recorded differences",
    )

    # The earlier immutable snapshot precedes the outer proxy operation settling.
    archived = _resolve(repo, "report", n["report_ref"], AssessmentReport)
    ledger = _resolve(
        repo, "operation_ledger", archived.operation_ledger_digest, AssessmentOperationLedger
    )
    (original,) = [row for row in ledger.operations if row.elapsed_seconds is None]
    final = _settled(repo, original.operation_id)
    require(
        final.plan_id == plan_n.plan_id
        and final.stage == "repository_development_proxy_lifecycle"
        and final.model_copy(
            update={"accounting": None, "resources": None, "elapsed_seconds": None}
        )
        == original,
        "the ordinary control's outer operation does not match its original reservation",
    )

    overhead = _settled(repo, plan_a.plan_id + ":external-scheduler")
    require(
        overhead.plan_id == plan_a.plan_id
        and overhead.stage == "external_scheduler"
        and overhead.reserved.max_model_turns == 0,
        "external scheduler overhead does not match the ASE plan",
    )
    return {
        "schema_version": "aeep.c13.evaluator-head-to-head.v1",
        "unique_tasks": 1,
        "engine_arms": [a, m],
        "earlier_ordinary_codex_control": n,
        "engine_pair_exact_matched_fields": list(keys),
        "engine_environments_match_after_excluding_environment_id": True,
        "observed_managed_minus_ase": {
            metric: m[metric] - a[metric]
            for metric in (
                "grade",
                "reported_input_plus_output",
                "agent_wall_seconds",
                "protected_grading_seconds",
            )
        },
        "ordinary_control_post_report_proxy_operation": {
            "historical_open_ref": content_digest(original),
            "settled_measurement_ref": content_digest(final),
            "elapsed_seconds": final.elapsed_seconds,
            "scope": "Whole parent operation for the original campaign; may overlap task operations.",
        },
        "engine_recipe_and_task_identity_adaptations": [
            "action_id",
            "template_family",
            "recipe_id",
            "recipe_description",
            "template_families",
        ],
        "external_scheduler_exclusive_charge_ref": content_digest(overhead),
        "external_scheduler_exclusive_seconds": overhead.elapsed_seconds,
        "ordinary_control_differences": native_differences,
        "ordinary_control_eligible_for_same_pair": False,
        "tokens_semantics": "Provider-reported. Cached input is included in input. Reasoning is included in output.",
        "provider_meter_independently_verified": False,
        "formal_candidate_usefulness": "NOT_ASSESSED",
        "formal_selection_usefulness": "NOT_ASSESSED",
        "new_task_executions": 0,
        "retained_input_pins": {
            str(path.relative_to(HERE.parent)): file_digest(path)
            for path in (
                RETAINED,
                ENGINE_RUNS / "completion-audit.json",
                CONTROL / "model-result.json",
                CONTROL / "completion-audit.json",
            )
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    with (
        ReceiptStore(args.ledger.resolve(strict=True), read_only=True) as store,
        patch.object(socket.socket, "connect", side_effect=AssertionError("network denied")),
    ):
        print(json.dumps(audit(AssessmentRepository(store)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
