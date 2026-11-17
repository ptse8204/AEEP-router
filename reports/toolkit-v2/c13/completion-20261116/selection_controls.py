"""Execute reviewed discovery-only and fixed selection policies over the same guarded pool."""

import time
from pathlib import Path
from typing import Literal

from capture_selection_route import finalize_selection, reserve_selection, selection_inputs
from pydantic import Field

from aeep.assessment.identity import protected_directory
from aeep.assessment.models import (
    AssessmentPlan,
    AssessmentReport,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.discovery import (
    DiscoveryRequest,
    DiscoveryResult,
    FixtureRegistryAdapter,
    _metadata_digest,
)
from aeep.discovery_service import DiscoveryService
from aeep.errors import ConfigurationError
from aeep.models import RouteDecision, StrictModel, UtcDateTime, utc_now
from aeep_toolkit.install_runtime import canonical, file_digest
from aeep_toolkit.models import Digest, Identifier, Measure

DEFINITION = "toolkit_selection_control_definition"
PRIOR = "toolkit_selection_fixed_prior"
OBSERVATION = "toolkit_selection_control_observation"


class CatalogCandidate(StrictModel):
    executor_id: Identifier
    raw_metadata_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class DiscoveryDefinition(StrictModel):
    policy: Literal["discovery-only"] = "discovery-only"
    study_ref: Digest
    driver_ref: Digest
    snapshot_path: str
    snapshot_sha256: Digest
    query: DiscoveryRequest
    candidates: dict[str, CatalogCandidate] = Field(min_length=1, max_length=24)


class FixedPrior(StrictModel):
    source_kind: Literal["assessment_report", "engineering_fixture"]
    source_report_ref: Digest
    development_task_refs: tuple[Digest, ...] = Field(min_length=1, max_length=10000)
    preferred_executor: Identifier
    observed_at: UtcDateTime


class FixedDefinition(StrictModel):
    policy: Literal["fixed"] = "fixed"
    study_ref: Digest
    driver_ref: Digest
    prior_ref: Digest
    frozen_at: UtcDateTime


class ControlObservation(StrictModel):
    scope_ref: Digest
    definition_ref: Digest
    operation_id: Identifier
    choice_id: Identifier
    guard_id: Identifier
    guard_ref: Digest
    source_id: str
    source_ref: Digest
    ordered_executors: tuple[Identifier, ...]
    shared_router_seconds: Measure
    preference_seconds: Measure


def require(condition, message):
    if not condition:
        raise ConfigurationError(message)


def load_definition(repo, request, scope, ref):
    model = DiscoveryDefinition if scope.policy == "discovery-only" else FixedDefinition
    definition = model.model_validate(repo.get(DEFINITION, ref))
    require(
        ref in request.definition_digests and content_digest(definition) == ref
        and definition.study_ref == scope.study_ref and definition.policy == scope.policy
        and definition.driver_ref == file_digest(Path(__file__)),
        "control policy is not bound to the reviewed study and exact driver",
    )
    return definition


class FixturePrior(StrictModel):
    study_ref: Digest
    prior_input_refs: tuple[Digest, ...]


def verify_prior_source(repo, scope, prior):
    if prior.source_kind == "engineering_fixture":
        study = repo.get("selection_fixture_study", scope.study_ref)
        fixture = FixturePrior.model_validate(repo.get("selection_fixture_prior", prior.source_report_ref))
        require(
            content_digest(study) == scope.study_ref and content_digest(fixture) == prior.source_report_ref
            and fixture.study_ref == scope.study_ref and fixture.prior_input_refs == prior.development_task_refs,
            "fixture observations cannot govern a real control policy",
        )
        return
    report = AssessmentReport.model_validate(repo.get("report", prior.source_report_ref))
    plan = AssessmentPlan.model_validate(repo.get("plan", report.plan_digest))
    with repo.store._lock:
        job = repo.store._connection.execute(
            "SELECT 1 FROM assessment_jobs WHERE report_id=? AND plan_id=? AND state='complete' AND error_code IS NULL",
            (report.report_id, plan.plan_id),
        ).fetchone()
    require(
        job is not None and content_digest(report) == prior.source_report_ref
        and content_digest(plan) == report.plan_digest and report.created_at == prior.observed_at
        and {content_digest(case.action.input) for case in plan.suite.cases} == set(prior.development_task_refs),
        "fixed policy requires a completed canonical prior report and its exact task inventory",
    )


def prior_preference(repo, request, scope, definition, decision_time):
    prior = FixedPrior.model_validate(repo.get(PRIOR, definition.prior_ref))
    require(
        content_digest(prior) == definition.prior_ref and definition.prior_ref in request.definition_digests
        and prior.observed_at <= definition.frozen_at <= decision_time
        and len(set(prior.development_task_refs)) == len(prior.development_task_refs)
        and scope.task_sha256 not in prior.development_task_refs
        and prior.preferred_executor in {scope.baseline_executor_id, *scope.candidates_by_executor},
        "fixed preference is outside approved prior development evidence",
    )
    verify_prior_source(repo, scope, prior)
    return prior


def discovery_order(definition, scope, result):
    query_ref = _metadata_digest({"public_query": definition.query.public_query})
    require(
        result.query_digest == query_ref
        and len(definition.query.source_ids) == len(result.source_records) == 1
        and result.source_records[0].source_id == definition.query.source_ids[0]
        and result.source_records[0].status == "complete"
        and result.source_records[0].adapter_id == "fixture"
        and result.candidate_ids == [candidate.registry_candidate_id for candidate in result.candidates]
        and result.candidate_ids == result.source_records[0].candidate_ids,
        "catalog metadata result is incomplete, stale or outside the reviewed source",
    )
    require(
        {binding.executor_id for binding in definition.candidates.values()} == set(scope.candidates_by_executor)
        and len(definition.candidates) == len(scope.candidates_by_executor),
        "discovery mapping does not expose the same candidate inventory",
    )
    ordered = []
    for candidate in result.candidates:
        binding = definition.candidates.get(candidate.registry_candidate_id)
        if binding is not None:
            require(binding.raw_metadata_digest == candidate.raw_metadata_digest, "reviewed catalog identity changed")
            ordered.append(binding.executor_id)
    return tuple(ordered)


def ranked_choice(scope, guard, ordered):
    available = {item.executor_id for item in guard.candidates if item.feasible}
    permitted = {scope.baseline_executor_id, *scope.candidates_by_executor}
    require(available <= permitted, "hard guard returned an executor outside the reviewed inventory")
    return next((item for item in (*ordered, scope.baseline_executor_id) if item in available), None)


async def capture_control(router, scope_ref, action, definition_ref):
    started = time.perf_counter()
    repo, scope, request = selection_inputs(router, scope_ref, action)
    require(scope.policy in {"fixed", "discovery-only"}, "expected a reviewed control arm")
    definition = load_definition(repo, request, scope, definition_ref)
    operation = reserve_selection(repo, scope, request)
    # Use the unchanged Router to enforce its current hard checks. Its score and
    # preferred executor do not participate in either control's ordering.
    guard = router.route(action)
    guard_saved = repo.store.get_decision(guard.decision_id)
    require(guard_saved is not None, "common feasibility audit was not stored")

    policy_started = time.perf_counter()
    if isinstance(definition, FixedDefinition):
        prior = prior_preference(repo, request, scope, definition, utc_now())
        ordered = (prior.preferred_executor,)
        source_id, source_ref = definition.prior_ref, content_digest(prior)
    else:
        path = canonical(definition.snapshot_path)
        require(
            not protected_directory(path) and not path.is_symlink()
            and path.stat().st_size <= 1_000_000 and file_digest(path) == definition.snapshot_sha256
            and len(definition.query.source_ids) == 1 and definition.query.cursor is None,
            "exact local public catalog snapshot changed",
        )
        service = DiscoveryService(
            router.store, {definition.query.source_ids[0]: FixtureRegistryAdapter(path)},
            max_results=definition.query.limit, timeout_seconds=scope.reserved_seconds,
        )
        found = await service.search(definition.query)
        require(file_digest(path) == definition.snapshot_sha256, "catalog snapshot changed during lookup")
        ordered = discovery_order(definition, scope, found)
        source_id, source_ref = found.discovery_id, content_digest(found)
    selected = ranked_choice(scope, guard, ordered)
    policy_seconds = time.perf_counter() - policy_started
    decision = RouteDecision(
        action=guard.action, policy=guard.policy, selected_executor_id=selected,
        baseline_executor_id=scope.baseline_executor_id, routing_overhead_ms=(time.perf_counter() - started) * 1000,
        candidates=[
            item.model_copy(update={"score": None, "rank": None, "cache_affinity": None})
            for item in sorted(guard.candidates, key=lambda item: item.executor_id)
        ],
        explanation=f"Reviewed {scope.policy} choice after common feasibility checks.",
    )
    # Store as study evidence only. BenchmarkRunner pins the selected executor in
    # a separate dispatch decision and checks the active grant again.
    router._persist_decision(decision)
    evidence = ControlObservation(
        scope_ref=scope_ref, definition_ref=definition_ref, operation_id=operation,
        choice_id=decision.decision_id, guard_id=guard.decision_id, guard_ref=content_digest(guard_saved),
        source_id=source_id, source_ref=source_ref, ordered_executors=ordered,
        shared_router_seconds=guard.routing_overhead_ms / 1000, preference_seconds=policy_seconds,
    )
    ref = repo.put(OBSERVATION, operation, evidence)
    return finalize_selection(repo, scope_ref, scope, request, operation, action, decision, started, control_ref=ref)


def verify_control(repo, scope, capture, decision):
    evidence = ControlObservation.model_validate(repo.get(OBSERVATION, capture.control_ref or ""))
    request = RecipeMaterializationRequest.model_validate(repo.get("recipe_materialization_request", scope.request_id))
    definition = load_definition(repo, request, scope, evidence.definition_ref)
    guard = repo.store.get_decision(evidence.guard_id)
    require(
        content_digest(evidence) == capture.control_ref
        and evidence.scope_ref == capture.scope_ref and evidence.operation_id == capture.operation_id
        and evidence.choice_id == decision.decision_id
        and guard is not None and content_digest(guard) == evidence.guard_ref
        and guard.decision_id != decision.decision_id and guard.created_at <= decision.created_at
        and guard.action == decision.action and guard.policy == decision.policy
        and {(row.executor_id, row.feasible) for row in guard.candidates}
            == {(row.executor_id, row.feasible) for row in decision.candidates}
        and not any(row.score is not None or row.rank is not None for row in decision.candidates)
        and evidence.shared_router_seconds == guard.routing_overhead_ms / 1000
        and evidence.shared_router_seconds + evidence.preference_seconds <= capture.router_seconds,
        "control choice or shared feasibility evidence changed",
    )
    if isinstance(definition, FixedDefinition):
        source = prior_preference(repo, request, scope, definition, decision.created_at)
        require(evidence.source_id == definition.prior_ref, "fixed prior binding changed")
        ordered = (source.preferred_executor,)
    else:
        source = DiscoveryResult.model_validate(repo.get("discovery_result", evidence.source_id))
        require(guard.created_at <= source.created_at <= decision.created_at, "catalog result is outside the decision")
        ordered = discovery_order(definition, scope, source)
    require(
        content_digest(source) == evidence.source_ref and ordered == evidence.ordered_executors
        and ranked_choice(scope, guard, ordered) == decision.selected_executor_id,
        "control source or reviewed ordering differs from the recorded decision",
    )
