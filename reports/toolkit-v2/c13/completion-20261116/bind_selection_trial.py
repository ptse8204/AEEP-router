"""Bind a pre-task selection to one ordinary benchmark execution and protected grade."""

import hashlib
import json
import sqlite3
from contextlib import closing
from itertools import combinations

from capture_selection_route import (
    CAPTURE,
    SelectionRouteCapture,
    implementation_source,
    load_scope,
    require_selected,
    resolve_route,
)

from aeep.assessment.identity import protected_directory
from aeep.assessment.models import RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.attempts import ExecutionAttemptState
from aeep.benchmarking import BenchmarkSuite, BenchmarkTrial, _pin_action
from aeep.economic.prepared import deterministic_digest, executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.hosts.codex_accounting import TOKEN_FIELDS
from aeep.models import ExecutionReceipt, StrictModel, UtcDateTime, ValidationResult, utc_now
from aeep.qualification import behavior_fingerprint
from aeep_toolkit.install_runtime import canonical
from aeep_toolkit.models import Digest, Identifier
from aeep_toolkit.selection import SelectionCase, SelectionDecision
from aeep_toolkit.telemetry import token_capture
from aeep_toolkit.workflow_evidence import _settled, open_store

APPROVAL = "toolkit_selection_trial_approval"
TRIAL = "toolkit_selection_trial_binding"
GRADE = "toolkit_selection_protected_grade"
GRADE_STAGE = "recipe_grading"
FRESH = {"process-cold", "router-fresh", "fresh-worker"}


class ApprovedTrial(StrictModel):
    scope_ref: Digest
    case_ref: Digest
    condition: Identifier
    database: str


class SelectedTrial(StrictModel):
    scope_ref: Digest
    capture_ref: Digest
    suite_ref: Digest
    request_ref: Digest
    approval_ref: Digest
    database: str
    selected_executor: Identifier
    executor_behavior_sha256: Digest
    executor_fingerprint: str
    execution_environment_ref: Digest
    bound_at: UtcDateTime

    def grade_operation(self):
        return "selection-grade:" + content_digest(self.model_dump(mode="json"))


class ProtectedGrade(StrictModel):
    binding_ref: Digest
    trial_id: str
    receipt_ref: Digest
    grader_definition_ref: Digest
    measurement_ref: Digest
    result: ValidationResult


def require(condition, message):
    if not condition:
        raise ConfigurationError(message)


def selection_snapshot(repo, scope_ref, case):
    scope = load_scope(repo, scope_ref)
    choice, _ = resolve_route(repo, scope_ref, study_ref=scope.study_ref, case=case)
    record = SelectionRouteCapture.model_validate(repo.get(CAPTURE, scope.operation_id()))
    require(_settled(repo, record.operation_id).plan_id == scope.request_id, "selection operation did not settle")
    decision = repo.store.get_decision(record.decision_id)
    selected = require_selected(decision, {scope.baseline_executor_id, *scope.candidates_by_executor})
    return scope, record, decision, selected, choice


def suite_position(suite, scope, case, selected):
    require(
        len(suite.cases) == len(suite.routes) == len(suite.conditions) == suite.repetitions == 1
        and not suite.warmup_cases and suite.conditions[0] in FRESH,
        "selection handoff requires one fresh pinned benchmark slot",
    )
    task, route = suite.cases[0], suite.routes[0]
    require(
        task.case_id == case.case_id == scope.case_id and task.fixture_files is None
        and content_digest(task.action) == scope.action_sha256
        and content_digest(task.action.input) == case.task_sha256
        and route.route_id == scope.policy and route.executor_id == selected
        and len(task.validators) == 1 and task.validators[0].kind == "callback",
        "pinned benchmark case, policy, executor or grader differs from the selection",
    )
    identity = f"trial_{suite.suite_id}_{task.case_id}_{route.route_id}_{suite.conditions[0]}_0"
    return task, identity


def benchmark_environment(router):
    # Match the ordinary runner's separately graded environment identity.
    identity = {
        "executors": [item.model_dump(mode="json") for item in router.registry.all()],
        "policies": {key: policy.model_dump(mode="json") for key, policy in router.manifest.policies.items()},
        "resources": [item.model_dump(mode="json") for item in router.manifest.resources],
        "separate_grading": True,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def approved_trial(repo, request, approval_ref, scope_ref, task, condition, database):
    approval = ApprovedTrial.model_validate(repo.get(APPROVAL, approval_ref))
    require(
        approval_ref in request.definition_digests and content_digest(approval) == approval_ref
        and approval.scope_ref == scope_ref and approval.case_ref == content_digest(task)
        and approval.condition == condition and approval.database == database,
        "protected case, grader or benchmark path differs from the reviewed pre-task definition",
    )


def bind_before_dispatch(router, scope_ref, case, suite, database, approval_ref):
    """Record the exact one-slot suite after selection and before opening the runner."""
    repo = AssessmentRepository(router.store)
    scope, capture, _, selected, _ = selection_snapshot(repo, scope_ref, case)
    task, _ = suite_position(suite, scope, case, selected)
    request = RecipeMaterializationRequest.model_validate(
        repo.get("recipe_materialization_request", scope.request_id)
    )
    path = canonical(str(database))
    require(
        not path.exists() and path.name == "campaign.sqlite3" and not protected_directory(path)
        and content_digest(router.manifest) == scope.manifest_sha256
        and implementation_source() == scope.source_sha256
        and {scope_ref, scope.study_ref} <= set(request.definition_digests),
        "selection context changed or benchmark was already opened",
    )
    repo.authorize(request)
    approved_trial(repo, request, approval_ref, scope_ref, task, suite.conditions[0], str(path))
    spec = router.registry.get(selected)
    record = SelectedTrial(
        scope_ref=scope_ref, capture_ref=content_digest(capture), suite_ref=content_digest(suite),
        request_ref=content_digest(request), approval_ref=approval_ref, database=str(path), selected_executor=selected,
        executor_behavior_sha256=behavior_fingerprint(spec), executor_fingerprint=executor_fingerprint(spec),
        execution_environment_ref=benchmark_environment(router), bound_at=utc_now(),
    )
    digest = repo.put(TRIAL, scope.operation_id(), record)
    return record, digest


def read_trial(binding, suite_id, trial_id):
    path = canonical(binding.database)
    require(
        path.is_file() and path.stat().st_nlink == 1 and path.name == "campaign.sqlite3"
        and not protected_directory(path),
        "benchmark store path differs",
    )
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        suite = connection.execute("SELECT content_sha256 FROM suites WHERE suite_id=?", (suite_id,)).fetchone()
        environment = connection.execute("SELECT content_sha256 FROM environments WHERE suite_id=?", (suite_id,)).fetchone()
        require(
            suite == (binding.suite_ref,) and environment == (binding.execution_environment_ref,),
            "benchmark inventory, policies or suite changed after selection",
        )
        trial_rows = connection.execute("SELECT state,payload_json FROM trials WHERE trial_id=?", (trial_id,)).fetchall()
        receipt_rows = connection.execute("SELECT payload_json FROM trial_receipts WHERE trial_id=?", (trial_id,)).fetchall()
        location = connection.execute("SELECT database_path FROM trial_stores WHERE trial_id=?", (trial_id,)).fetchone()
    require(
        len(trial_rows) == len(receipt_rows) == 1 and trial_rows[0][0] == "complete" and location is not None,
        "canonical slot does not have one completed trial and one receipt",
    )
    attempt_store = canonical(location[0])
    require(
        attempt_store.parent == path.parent / "attempts"
        and attempt_store.suffix == ".sqlite3" and attempt_store != path,
        "trial attempt store is outside the bound benchmark run",
    )
    trial = BenchmarkTrial.model_validate_json(trial_rows[0][1])
    receipt = ExecutionReceipt.model_validate_json(receipt_rows[0][0])
    return trial, receipt, attempt_store


def verify_attempt(path, receipt, task, choice, selected, binding):
    with closing(open_store(str(path))) as store:
        attempt = store.get_execution_attempt(receipt.metadata.get("attempt_id", ""))
        persisted = store.get_receipt(receipt.receipt_id)
        decision = store.get_decision(receipt.decision_id)
        pinned = _pin_action(task.action, selected)
        require(
            decision is not None and persisted == receipt and attempt is not None
            and attempt.state is ExecutionAttemptState.COMPLETED
            and choice.decision_id != decision.decision_id == attempt.decision_id
            and receipt.receipt_id in attempt.terminal_receipt_ids
            and receipt.executor_id == attempt.executor_id == decision.selected_executor_id == selected
            and receipt.executor_fingerprint == attempt.executor_fingerprint == binding.executor_fingerprint
            and receipt.action_id == choice.action.action_id == decision.action.action_id
            and decision.action.capability == pinned.capability == receipt.capability
            and decision.action.constraints.allowed_executor_ids == [selected]
            and decision.action.input == {"__aeep_redacted__": True}
            and binding.bound_at <= decision.created_at <= receipt.started_at <= receipt.ended_at
            and attempt.action_digest == deterministic_digest({
                "capability": pinned.capability, "input": pinned.input, "constraints": pinned.constraints,
            }),
            "execution receipt or action differs from the selected benchmark handoff",
        )
        journal_ref = receipt.metadata.get("execution_evidence_digest", "")
        journal = ExecutionEvidence.model_validate(AssessmentRepository(store).get("execution_evidence", journal_ref))
        require(
            content_digest(journal) == journal_ref and journal.complete
            and journal.attempt_id == attempt.attempt_id and journal.events[-1].kind == "execution.completed",
            "protected task execution has no matching terminal journal",
        )
    return journal


def checked_binding(repo, scope_ref, case, suite):
    scope, capture, choice, selected, value = selection_snapshot(repo, scope_ref, case)
    task, trial_id = suite_position(suite, scope, case, selected)
    binding = SelectedTrial.model_validate(repo.get(TRIAL, scope.operation_id()))
    request = RecipeMaterializationRequest.model_validate(
        repo.get("recipe_materialization_request", scope.request_id)
    )
    require(
        binding.scope_ref == scope_ref and binding.capture_ref == content_digest(capture)
        and binding.suite_ref == content_digest(suite) and binding.selected_executor == selected
        and binding.request_ref == content_digest(request) and binding.bound_at >= capture.captured_at
        and {scope_ref, scope.study_ref} <= set(request.definition_digests),
        "canonical benchmark binding differs from the pre-task selection",
    )
    approved_trial(repo, request, binding.approval_ref, scope_ref, task, suite.conditions[0], binding.database)
    return scope, choice, selected, value, task, trial_id, binding, request


def authorize_trial(repo, scope_ref, case, suite, router, route, trial):
    """Recheck the bound selection in BenchmarkRunner's before-trial hook."""
    (scope, _, selected, _, _, trial_id, binding, request) = checked_binding(repo, scope_ref, case, suite)
    path = canonical(router.store.path)
    require(
        trial.trial_id == trial_id and trial.case_id == scope.case_id and trial.state == "running"
        and trial.route_id == scope.policy and trial.condition == suite.conditions[0]
        and route == suite.routes[0] and route.executor_id == selected
        and trial.started_at >= binding.bound_at
        and path.parent == canonical(binding.database).parent / "attempts"
        and benchmark_environment(router) == binding.execution_environment_ref,
        "runner slot or execution environment differs from the approved selection",
    )
    repo.authorize(request)
    return request


def observed_tokens(receipt, journal, trial):
    capture = token_capture(receipt, journal if "codex_token_fields" in receipt.metadata else None)
    fields = capture["known_fields"]
    require(
        all(getattr(trial.actual_resources, field) == getattr(receipt.actual_resources, field) for field in fields),
        "captured tokens differ from the canonical trial",
    )
    counts = {field: getattr(receipt.actual_resources, field) if field in fields else None
              for field in TOKEN_FIELDS.values()}
    incoming, outgoing = counts["input_tokens"], counts["output_tokens"]
    return {
        "capture": capture,
        "provider_model": receipt.metadata.get("actual_model") if fields else None,
        "raw_counts": counts,
        "cache_semantics": "included_in_input" if fields else None,
        "reasoning_semantics": "included_in_output" if fields else None,
        "input_plus_output_tokens": incoming + outgoing if incoming is not None and outgoing is not None else None,
    }


def resolved_case_measurements(resolved):
    """Compare measurements from resolve_outcome for one case across policies."""
    shared_fields = (
        "study_ref", "task_ref", "action_ref", "condition", "grader_definition_ref", "shared_environment_ref",
    )
    require(len(resolved) >= 2 and len({choice.case_id for choice, _ in resolved}) == 1
            and len({choice.policy for choice, _ in resolved}) == len(resolved)
            and len({choice.decision_ref for choice, _ in resolved}) == len(resolved)
            and len({proof["receipt_ref"] for _, proof in resolved}) == len(resolved)
            and all(len({proof[field] for _, proof in resolved}) == 1 for field in shared_fields)
            and all(choice.task_verified is not None and choice.verification_ref == content_digest(proof)
                    and proof["tokens"]["capture"]["receipt_ref"] == proof["receipt_ref"]
                    for choice, proof in resolved),
            "matched selection observations require distinct verified policies for the same case")
    comparisons = []
    for (left, a), (right, b) in combinations(resolved, 2):
        a_tokens, b_tokens = a["tokens"], b["tokens"]
        comparable = a_tokens["provider_model"] is not None and all(
            a_tokens[key] == b_tokens[key] for key in ("provider_model", "cache_semantics", "reasoning_semantics")
        ) and all(a_tokens["capture"][key] == b_tokens["capture"][key] for key in ("source", "trust"))
        a_counts, b_counts = a_tokens["raw_counts"], b_tokens["raw_counts"]
        pair = {
            "left": left.policy, "right": right.policy,
            "left_grade_ref": a["grade_ref"], "right_grade_ref": b["grade_ref"],
            "verified_success_left_minus_right": int(left.task_verified) - int(right.task_verified),
            "quality_score_left_minus_right": a["quality_score"] - b["quality_score"],
            "token_capture_status": {left.policy: a_tokens["capture"]["status"],
                                     right.policy: b_tokens["capture"]["status"]},
            "raw_token_differences_left_minus_right": {
                field: left_count - b_counts[field]
                if comparable and left_count is not None and b_counts[field] is not None else None
                for field, left_count in a_counts.items()
            },
        }
        a_total, b_total = a_tokens["input_plus_output_tokens"], b_tokens["input_plus_output_tokens"]
        pair["input_plus_output_left_minus_right"] = (
            a_total - b_total if comparable and a_total is not None and b_total is not None else None
        )
        for field in ("decision_seconds", "agent_seconds", "grading_seconds"):
            pair[f"{field}_left_minus_right"] = a[field] - b[field] if a[field] is not None and b[field] is not None else None
        comparisons.append(pair)
    return {
        "case_id": resolved[0][0].case_id,
        "policies": {
            choice.policy: {"decision_ref": choice.decision_ref, "selected": choice.selected,
                            "task_verified": choice.task_verified, "verification_ref": choice.verification_ref,
                            **proof}
            for choice, proof in resolved
        },
        "comparisons": comparisons,
    }


def resolve_outcome(repo, scope_ref: str, case: SelectionCase, suite: BenchmarkSuite) -> tuple[SelectionDecision, dict]:
    """Reconstruct one graded selection row from read-only canonical records."""
    scope, choice, selected, value, task, trial_id, binding, request = checked_binding(repo, scope_ref, case, suite)
    trial, receipt, store = read_trial(binding, suite.suite_id, trial_id)
    require(
        trial.trial_id == trial_id and trial.suite_id == suite.suite_id and trial.run_id == f"run_{binding.suite_ref}"
        and trial.case_id == case.case_id and trial.route_id == scope.policy
        and trial.condition == suite.conditions[0] and trial.repetition == 0
        and trial.state == "complete" and trial.status == "success" and trial.ok
        and trial.receipt_ids == [receipt.receipt_id] and trial.retry_fallback_count == 0
        and trial.route_fingerprint == binding.executor_behavior_sha256
        and len(trial.case_validation) == 1 and trial.valid is not None
        and receipt.status == "success" and receipt.execution_success is True
        and trial.ended_at is not None
        and binding.bound_at <= trial.started_at <= receipt.started_at <= receipt.ended_at <= trial.ended_at,
        "benchmark trial did not finish the exact selected route and grader",
    )
    charge = _settled(repo, trial_id)
    require(
        charge.plan_id == request.plan_id and charge.stage == "trial"
        and trial.started_at <= charge.started_at <= receipt.started_at,
        "execution reservation was not bound to the selected trial",
    )
    journal = verify_attempt(store, receipt, task, choice, selected, binding)
    grade = ProtectedGrade.model_validate(repo.get(GRADE, binding.grade_operation()))
    measurement = _settled(repo, binding.grade_operation())
    result = trial.case_validation[0]
    require(
        grade.binding_ref == content_digest(binding) and grade.trial_id == trial_id
        and grade.receipt_ref == content_digest(receipt)
        and grade.grader_definition_ref == content_digest(task.validators[0])
        and grade.measurement_ref == content_digest(measurement)
        and measurement.plan_id == request.plan_id and measurement.stage == GRADE_STAGE
        and measurement.reserved.max_model_turns == 0 and measurement.reserved.max_cash_usd == 0
        and receipt.ended_at <= measurement.started_at <= trial.ended_at
        and result == grade.result and result.kind == "callback" and result.trust == "verified"
        and result.valid is trial.valid and result.quality_score is not None
        and trial.failure_category == (None if result.valid else "task_failure"),
        "protected grade or settled verification measure differs from the selected trial",
    )
    verification = {
        "study_ref": scope.study_ref, "task_ref": case.task_sha256, "action_ref": scope.action_sha256,
        "condition": trial.condition.value,
        "grader_definition_ref": grade.grader_definition_ref, "shared_environment_ref": binding.execution_environment_ref,
        "binding_ref": content_digest(binding), "trial_ref": content_digest(trial), "receipt_ref": grade.receipt_ref,
        "journal_ref": content_digest(journal), "trial_measurement_ref": content_digest(charge),
        "grade_ref": content_digest(grade), "grade_measurement_ref": grade.measurement_ref,
        "quality_score": result.quality_score, "decision_seconds": value.decision_wall_seconds,
        "agent_seconds": None if trial.wall_time_ms is None else trial.wall_time_ms / 1000,
        "grading_seconds": None if trial.grading_wall_time_ms is None else trial.grading_wall_time_ms / 1000,
        "tokens": observed_tokens(receipt, journal, trial),
        "execution_status": trial.status.value, "failure_category": trial.failure_category,
        "retry_fallback_count": trial.retry_fallback_count,
    }
    return value.model_copy(update={
        "task_verified": trial.valid, "verification_ref": content_digest(verification),
    }), verification
