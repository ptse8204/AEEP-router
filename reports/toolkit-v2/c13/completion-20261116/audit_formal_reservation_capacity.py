"""Check formal case capacity and trial reservations against retained evidence."""

import json
from collections import Counter
from contextlib import closing
from decimal import Decimal

import audit_corpus_capacity as corpus
from audit_formal_inputs import REQUIRED
from check_migrated_graders import DATABASE, HERE, ROOT

from aeep.assessment.models import AssessmentOperation, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.workflow_evidence import open_store

STUDY = HERE.parent / "managed-comparison-20261115"
DESIGN = STUDY / "sol-comparison-design.json"
SALES = STUDY / "sales-window-review.json"
AUTHORIZATION = "onboarding"


def ledger_balance():
    with closing(open_store(str(DATABASE))) as store:
        repository = AssessmentRepository(store)
        with store._lock:
            grant = repository.effective_grant(AUTHORIZATION)
            operations, turns, elapsed, cash, revoked = store._connection.execute(
                "SELECT operations, model_turns, elapsed_seconds, cash_usd, revoked "
                "FROM assessment_grants WHERE id=?", (AUTHORIZATION,),
            ).fetchone()
            reservations = store._connection.execute(
                "SELECT records.payload_json FROM assessment_operations AS operations "
                "JOIN assessment_records AS records ON records.kind='operation_start' "
                "AND records.id=operations.id WHERE operations.grant_id=? AND operations.state='reserved' "
                "ORDER BY operations.id", (AUTHORIZATION,),
            ).fetchall()
    pending = [AssessmentOperation.model_validate_json(row[0]) for row in reservations]
    limits = grant.limits
    remaining = {
        "operations": limits.max_operations - operations,
        "model_turns": limits.max_model_turns - turns,
        "elapsed_seconds": limits.max_elapsed_seconds - elapsed,
        "cash_usd": str(limits.max_cash_usd - Decimal(cash)),
    }
    return {
        "authorization_id": AUTHORIZATION,
        "effective_grant_sha256": content_digest(grant),
        "absolute_limits": limits.model_dump(mode="json"), "expires_at": grant.expires_at.isoformat(),
        "revoked": bool(revoked),
        "charged_including_pending": {"operations": operations, "model_turns": turns, "elapsed_seconds": elapsed,
                                      "cash_usd": cash},
        "remaining_including_pending": remaining,
        "unresolved_reservations": [
            {"record_sha256": content_digest(item), "stage": item.stage, "reserved": item.reserved.model_dump(mode="json")}
            for item in pending
        ],
    }


def stage(normal_deadline, arms, cases):
    # Use the managed-call allowance in AssessmentService.budget_preview.
    # The higher-compute arm has twice the normal deadline.
    deadlines = {arm: normal_deadline * (2 if arm == "higher_compute" else 1) for arm in arms}
    return {
        "case_count": cases, "route_deadline_seconds": deadlines,
        "trial_operations": cases * len(arms), "model_turns": cases * len(arms),
        "trial_reservation_seconds": cases * sum(seconds + 5 for seconds in deadlines.values()),
    }


def total(stages, balance):
    operations = sum(row["trial_operations"] for row in stages)
    turns = sum(row["model_turns"] for row in stages)
    seconds = sum(row["trial_reservation_seconds"] for row in stages)
    return {
        "operations": operations, "model_turns": turns, "trial_reservation_seconds": seconds,
        "operations_above_remaining": max(0, operations - balance["operations"]),
        "model_turns_above_remaining": max(0, turns - balance["model_turns"]),
        "trial_reservation_seconds_above_remaining": max(0, seconds - balance["elapsed_seconds"]),
    }


def source_capacity():
    rows, _ = corpus.prior_origins()
    for filename, field in corpus.EXTRA_INDEXES:
        record = corpus.load(HERE / filename)
        rows.extend(json.loads(corpus.read(ROOT / record[field], record[field + "_sha256"])))
    retained = corpus.load(HERE / "repository-capacity-audit.json")
    if Counter(row["input"]["family"] for row in rows) != retained["provisional_counts"]:
        raise ValueError("retained formal source pool differs from the audited projection")
    staged = HERE / "staged-repository-grader-bindings.json"
    blocked = {row["case"]: row["declared_requires_python"]
               for row in corpus.load(staged)["cases"] if row.get("admits_python_3_13_0") is False}
    known = {row["input"]["task_id"]: row["input"]["family"] for row in rows}
    if not blocked or not blocked.keys() <= known.keys():
        raise ValueError("retained runtime observations refer to a different source pool")
    remaining = Counter(family for case, family in known.items() if case not in blocked)
    additions = Counter(retained["proposed_counts"])
    family = "multi-file-repair"
    # Reuse the existing balanced-stage rule and compare one additional case.
    current = corpus.minimum_profiles(remaining, additions)
    extra = corpus.minimum_profiles(remaining, additions + Counter({family: 1}))
    return {
        "staged_runtime_audit_sha256": file_digest(staged),
        "source_review_sha256": retained["source_review_sha256"],
        "case_pool_sha256": file_digest(HERE / "repository-capacity-audit.json"),
        "python_3_13_exclusions": {case: {"requirement": spec, "family": known[case]} for case, spec in blocked.items()},
        "retained_counts_outside_known_runtime_exclusions": dict(remaining),
        "pending_source_counts": dict(additions),
        "balanced_profiles_using_only_pending_batch": [dict(plan[0]) for plan in current],
        "balanced_profiles_with_one_more_multifile_case": [dict(plan[0]) for plan in extra],
        "scope": "Population lower bound on the current runtime projection. Each compatible prospect still needs applicable protected evidence and source-disjoint assignment.",
    }


def audit():
    status = ledger_balance()
    balance = status["remaining_including_pending"]
    design, sales = (json.loads(path.read_bytes()) for path in (DESIGN, SALES))
    normal = design["maximum_live_scope"]["single_model_turn_timeout_seconds"]
    long = sales["deadline_seconds_both_arms"]
    if type(normal) is not int or type(long) is not int or not 0 < normal < long:
        raise ValueError("prior timing pins no longer match the two measured scopes")
    cases = sum(REQUIRED.values())
    arms = ("ordinary", "candidate", "higher_compute", "reusable_tool")
    qualification = stage(normal, ("candidate",), cases)
    marginal = stage(normal, arms, cases)
    catalog = stage(normal, arms, cases)
    selection = stage(normal, ("aeep", "discovery_only", "fixed"), REQUIRED["holdout"])
    return {
        "schema_version": "aeep.c13.formal-trial-reservation-scenarios.v1",
        "case_counts": REQUIRED, "operational_grant_snapshot": status,
        "current_python_3_13_case_capacity": source_capacity(),
        "retained_design_sha256": file_digest(DESIGN), "sales_followup_review_sha256": file_digest(SALES),
        "implementation_sha256": {name: file_digest(ROOT / "src/aeep/assessment" / name)
                                  for name in ("comparison.py", "service.py", "budget.py")},
        "retained_deadlines_seconds": {"development": normal, "sales_followup": long},
        "stage_examples_at_normal_development_deadline": {
            "qualification": qualification, "marginal_value": marginal, "native_catalog": catalog,
            "three_policy_selection_105_task_sizing_example": selection,
        },
        "projections": {
            "one_qualification_and_marginal_cohort": total([qualification, marginal], balance),
            "two_separate_qualification_and_marginal_cohorts": total([qualification, marginal] * 2, balance),
            "two_separate_qualification_marginal_and_catalog_cohorts": total([qualification, marginal, catalog] * 2, balance),
            "one_cohort_at_each_retained_deadline": total([
                qualification, marginal, stage(long, ("candidate",), cases), stage(long, arms, cases),
            ], balance),
            "two_qualification_and_marginal_cohorts_then_one_selection_example": total([
                qualification, marginal, qualification, marginal, selection,
            ], balance),
        },
        "scope": "Planning projections for one fresh worker condition, one repetition and one managed turn per route on the full schedule. Each conditional cohort has independent stage inputs.",
        "trial_reservation_scope": "Only model trial operations and their per-call reservation ceilings. The final canonical budget preview must add setup, router creation, grader validation, grading, reporting and any other reviewed costs.",
        "selection_example_scope": "The three-policy count shows 105 hypothetical independent tasks and supplies no selection threshold or scope decision.",
        "deadline_scope": "300 and 480 seconds come from retained development definitions. Actual formal settings require independent timing and a frozen plan.",
        "authorization_changed": False, "comparative_dispatch_approved": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, indent=2, allow_nan=False))
