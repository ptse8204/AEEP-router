"""Reconcile the measured scope of the six accepted SkillsBench CLI journeys."""

import json
import math
import runpy
from pathlib import Path
from statistics import median

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "canonical-stack-verification-20261113"
AUDITOR = PRIOR / "audit-domain-journeys.py"
AUDIT = PRIOR / "domain-journey-audit.json"


def agrees(left, right):
    return math.isfinite(left) and math.isfinite(right) and math.isclose(left, right, abs_tol=1e-8, rel_tol=0)


def profile(repo, task, settled):
    binding = task["run_wrapper"]
    operation = binding["operation_id"]
    charge = settled(repo, operation)
    receipt = ExecutionReceipt.model_validate(repo.get("toolkit_workflow_receipt", operation))
    meta = receipt.metadata
    if (
        content_digest(charge) != binding["measurement_ref"] or content_digest(receipt) != binding["receipt_ref"]
        or charge.stage != "workflow_run_overhead" or charge.resources != receipt.actual_resources
        or charge.resources is None or charge.elapsed_seconds is None
        or meta.get("observed_resource_dimensions") != ["latency_ms", "cpu_ms"]
        or meta.get("legacy_vector_defaults_are_not_observations") is not True
        or meta["workflow_accounting"]["operation_id"] != operation
    ):
        raise ValueError("settled wrapper resource evidence differs")
    nested, = meta["excluded_nested_intervals"]
    whole = meta["whole_wrapper_wall_seconds"]
    agent, grade = task["agent_wall_seconds"], task["protected_grading_wall_seconds"]
    if (
        nested["stage"] != "canonical_assessment_execution" or not 0 <= agent + grade <= nested["wall_seconds"] <= whole
        or not agrees(whole - nested["wall_seconds"], charge.elapsed_seconds)
        or not agrees(charge.elapsed_seconds * 1000, charge.resources.latency_ms)
        or not agrees((meta["whole_wrapper_process_cpu_seconds"] - nested["process_cpu_seconds"]) * 1000,
                      charge.resources.cpu_ms)
    ):
        raise ValueError("measured wrapper intervals do not reconcile")
    return {
        "task_id": task["task_id"], "workflow_configuration": task["workflow_configuration"],
        "implementation_source": task["original_source"], "report_ref": task["assessment_report_ref"],
        "trial_ref": task["trial_ref"], "worker_receipt_ref": task["receipt_ref"], "wrapper": binding,
        "protected_score": task["protected_score"], "retries": task["retries"],
        "whole_cli_wall_seconds_before_finalization": whole,
        "canonical_execution_wall_seconds": nested["wall_seconds"],
        "exclusive_wrapper_wall_seconds": charge.elapsed_seconds, "exclusive_wrapper_process_cpu_ms": charge.resources.cpu_ms,
        "agent_wall_seconds": agent, "protected_grading_wall_seconds": grade,
        "canonical_span_less_agent_and_grading_seconds": nested["wall_seconds"] - agent - grade,
        "existing_exclusive_reservation_seconds": charge.reserved.max_elapsed_seconds,
        "whole_host_peak_memory_mb": None, "whole_host_energy": None, "actual_provider_cash": None,
    }


def summarize(tasks):
    dimensions = (
        "whole_cli_wall_seconds_before_finalization", "canonical_execution_wall_seconds",
        "exclusive_wrapper_wall_seconds", "agent_wall_seconds", "protected_grading_wall_seconds",
    )
    return {
        key: {"observations": len(tasks), "min": min(values), "median": median(values), "max": max(values)}
        for key in dimensions if (values := [task[key] for task in tasks])
    }


def audit():
    original = runpy.run_path(str(AUDITOR))
    verified = original["audit"]()
    if verified != original["read"](AUDIT):
        raise ValueError("historical domain audit no longer matches its original scopes")
    database = original["read"](PRIOR / "domain-telemetry-preflight.json")["database"]
    domains = {}
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        for domain, rows in verified["domains"].items():
            tasks = [profile(repo, row, original["settled"]) for row in rows["tasks"]]
            if len(tasks) != 3:
                raise ValueError("expected three accepted integration tasks per domain")
            summary = summarize(tasks)
            longest = summary["whole_cli_wall_seconds_before_finalization"]["max"]
            domains[domain] = {
                "cases": tasks, "elapsed_seconds": summary,
                "suggested_serial_review_window_seconds": 60 * math.ceil(longest * 1.5 / 60),
            }
    if set(domains) != {"document-data", "software-engineering"}:
        raise ValueError("integration cohort changed")
    return {
        "schema_version": "aeep.c13.skillsbench-resource-observations.v1",
        "source_audit_sha256": original["sha"](AUDIT), "source_auditor_sha256": original["sha"](AUDITOR),
        "skillsbench_revision": verified["skillsbench_revision"], "domains": domains,
        "scope": "Six historical serial integration journeys. Whole CLI measurement stops before receipt persistence and Router close.",
        "canonical_remainder_scope": "Unattributed arithmetic difference within the measured canonical span.",
        "review_window_scope": "Planning signal only. Add 50 percent to each observed domain maximum and round up to a minute. Longer workloads, prior timeouts and concurrency require separate observation.",
        "unknown_resource_dimensions": ["whole_host_memory", "energy", "concurrent_capacity", "actual_provider_cash"],
        "timeouts_and_historical_comparisons_remain_separate": True,
        "new_model_calls": 0, "changed_authority": False, "resource_acceptance": "OPEN",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
