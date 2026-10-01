"""Timing pilots use ordinary campaigns and never supply holdout evidence."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..benchmarking import BenchmarkCampaignReport, BenchmarkPhase, BenchmarkSplit
from ..errors import ConfigurationError
from .models import (
    AssessmentEnvironment,
    AssessmentPlan,
    AssessmentReport,
    AssessmentRunBinding,
    AssessmentSubject,
    ReviewedMapping,
    content_digest,
)
from .repository import AssessmentRepository

if TYPE_CHECKING:
    from .service import AssessmentService


def require_separation(repository: AssessmentRepository, plan: AssessmentPlan) -> None:
    """Check both directions, including a pilot proposed after a main plan."""
    selected = {content_digest(case.action.input) for case in plan.suite.cases
                if plan.pilot is not None or case.split == BenchmarkSplit.HOLDOUT}
    other_kind = "IS NULL" if plan.pilot is not None else "IS NOT NULL"
    with repository.store._lock:
        rows = repository.store._connection.execute(
            "SELECT payload_json FROM assessment_records WHERE kind='plan' "
            "AND json_extract(payload_json, '$.subject_digest')=? "
            "AND json_extract(payload_json, '$.recipe_digest')=? AND id<>? "
            f"AND json_extract(payload_json, '$.pilot') {other_kind}",
            (plan.subject_digest, plan.recipe_digest, plan.plan_id)).fetchall()
    for row in rows:
        other = AssessmentPlan.model_validate_json(row[0])
        previous = {content_digest(case.action.input) for case in other.suite.cases
                    if other.pilot is not None or case.split == BenchmarkSplit.HOLDOUT}
        if selected & previous:
            raise ConfigurationError("timing pilot inputs cannot enter assessment holdout")


def timing_preview(service: AssessmentService, report_id: str, *, mapping: ReviewedMapping | None = None) -> dict[str, Any]:
    """Pool assigned arms without selecting on correctness or apparent benefit."""
    repository = service.repository
    report = AssessmentReport.model_validate(repository.get('report', report_id))
    plan = AssessmentPlan.model_validate(repository.get('plan', report.plan_digest))
    if plan.pilot is None:
        raise ConfigurationError('timing preview requires an explicit pilot plan')
    if mapping is None:
        service._verify_dependencies(plan)
    else:
        # Historical timing is read from the frozen mapping. The new mapping is
        # checked below; executing it still requires its own review and boundary.
        from .identity import verify_dependencies, verify_subject
        verify_dependencies(plan.executable_dependencies)
        verify_subject(AssessmentSubject.model_validate(repository.get('subject', plan.subject_digest)))
    from .verification import verification_source_digest
    binding = AssessmentRunBinding.model_validate(repository.get('run_binding', plan.plan_id))
    with repository.store._lock:
        complete = repository.store._connection.execute(
            "SELECT 1 FROM assessment_jobs WHERE plan_id=? AND report_id=? "
            "AND state='complete' AND error_code IS NULL", (plan.plan_id, report.report_id)).fetchone()
    if complete is None or binding.source_digest != verification_source_digest(Path(__file__).parents[3]):
        raise ConfigurationError('pilot timing requires a completed source-bound campaign')
    measured = _timing(repository, report, plan)
    if mapping is not None:
        _require_calibrated_mapping(repository, plan, mapping, measured['proposed_normal_deadline_seconds'])
    return {
        'pilot_plan_digest': content_digest(plan), 'pilot_report_digest': content_digest(report),
        **measured, 'requires_new_review': True,
        'authorization_changed': False, 'remaining': service.budget_preview(plan.plan_id)['remaining'],
        'explanation': 'Timing only. All assigned arms contribute; correctness does not select samples. '
                       'These inputs are excluded from holdout. Main sample counts and thresholds stay fixed. '
                       'A new reviewed main plan and sufficient authorization are required. '
                       'A missing deadline means measurements are incomplete or exceed the reviewed ceiling.',
    }


def _timing(repository: AssessmentRepository, report: AssessmentReport, plan: AssessmentPlan) -> dict[str, Any]:
    assert plan.pilot is not None
    campaign = BenchmarkCampaignReport.model_validate(repository.get('campaign', report.campaign_digest))
    if content_digest(campaign) != report.campaign_digest or campaign.suite_id != plan.suite.suite_id:
        raise ConfigurationError('pilot campaign identity differs')
    trials = [trial for trial in campaign.trials if trial.phase != BenchmarkPhase.SETUP]
    expected = {(case.case_id, route.route_id, plan.suite.conditions[0], 0)
                for case in plan.suite.cases for route in plan.suite.routes}
    observed = {(trial.case_id, trial.route_id, trial.condition, trial.repetition) for trial in trials}
    measured = (observed == expected and len(trials) == len(expected)
                and all(trial.wall_time_ms is not None and math.isfinite(trial.wall_time_ms)
                        and trial.wall_time_ms >= 0 and trial.ok for trial in trials))
    result: dict[str, Any] = {
        'complete_measurements': measured, 'assigned_executions': len(expected),
        'pooled_percentile_seconds': None, 'proposed_normal_deadline_seconds': None,
        'proposed_higher_deadline_seconds': None,
    }
    if measured:
        seconds = sorted(trial.wall_time_ms / 1000 for trial in trials if trial.wall_time_ms is not None)
        # Nearest-rank p95 is frozen in the reviewed pilot policy.
        pooled = seconds[math.ceil(plan.pilot.percentile / 100 * len(seconds)) - 1]
        deadline = max(plan.pilot.minimum_deadline_seconds, math.ceil(pooled * plan.pilot.deadline_multiplier))
        result['pooled_percentile_seconds'] = pooled
        higher = bool(plan.comparison and plan.comparison.experiment and plan.comparison.experiment.higher_compute)
        if deadline * (2 if higher else 1) <= plan.pilot.maximum_deadline_seconds:
            result['proposed_normal_deadline_seconds'] = deadline
            if higher:
                result['proposed_higher_deadline_seconds'] = 2 * deadline
    return result


def _require_calibrated_mapping(repository: AssessmentRepository, pilot: AssessmentPlan,
                                mapping: ReviewedMapping, deadline: float | None) -> None:
    previous = ReviewedMapping.model_validate(repository.get('mapping', pilot.mapping_digest))
    if content_digest(previous) != pilot.mapping_digest:
        raise ConfigurationError('pilot mapping identity differs')
    current = {spec.id: spec for spec in mapping.subjects}
    if len(current) != len(mapping.subjects):
        raise ConfigurationError('pilot calibration requires distinct implementation IDs')
    for spec in previous.subjects:
        if spec.id not in current:
            raise ConfigurationError('pilot calibration cannot remove a reviewed implementation')
        before, after = spec.model_dump(mode='json'), current[spec.id].model_dump(mode='json')
        prior_timeout = before['config'].pop('timeout_seconds', 60)
        timeout = after['config'].pop('timeout_seconds', 60)
        primary = spec.id in {pilot.candidate_id, pilot.baseline_id}
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
                or before != after or (timeout != prior_timeout and (not primary or deadline is None or timeout != deadline))):
            raise ConfigurationError('pilot calibration permits only its measured primary-arm deadline change')


def require_linked_pilot(repository: AssessmentRepository, plan: AssessmentPlan) -> AssessmentPlan | None:
    """Bind measured pilot costs once without charging them again."""
    if plan.pilot_report_digest is None:
        return None
    report = AssessmentReport.model_validate(repository.get('report', plan.pilot_report_digest))
    previous = AssessmentPlan.model_validate(repository.get('plan', report.plan_digest))
    with repository.store._lock:
        complete = repository.store._connection.execute(
            "SELECT 1 FROM assessment_jobs WHERE plan_id=? AND report_id=? "
            "AND state='complete' AND error_code IS NULL", (previous.plan_id, report.report_id)).fetchone()
    if (previous.pilot is None or complete is None
            or content_digest(report) != plan.pilot_report_digest
            or content_digest(previous) != report.plan_digest
            or content_digest(previous) not in plan.definition_digests
            or previous.plan_id not in (plan.preparation_request_ids or [])
            or any(getattr(previous, field) != getattr(plan, field) for field in
                   ('subject_digest','recipe_digest','authorization_id','candidate_id','baseline_id'))
            or (previous.executable_dependencies != plan.executable_dependencies
                if plan.schema_version != 'assessment.plan.v6'
                else any(plan.executable_dependencies.get(key) != value
                         for key, value in previous.executable_dependencies.items()))):
        raise ConfigurationError('pilot evidence differs from the reviewed task, environment or runtime')
    prior_environment = AssessmentEnvironment.model_validate(repository.get('environment', previous.environment_digest))
    current_environment = AssessmentEnvironment.model_validate(repository.get('environment', plan.environment_digest))
    # Additional challenger profiles may be reviewed after the two-arm pilot;
    # its own workers and resource/security policy must remain identical.
    ignored = {'environment_id', 'conformance_digests'}
    calibrated = plan.schema_version == 'assessment.plan.v6'
    if calibrated:
        mapping = ReviewedMapping.model_validate(repository.get('mapping', plan.mapping_digest))
        if content_digest(mapping) != plan.mapping_digest:
            raise ConfigurationError('main mapping identity differs')
        measured = _timing(repository, report, previous)
        if measured['proposed_normal_deadline_seconds'] is None:
            raise ConfigurationError('pilot measurements cannot establish a bounded deadline')
        _require_calibrated_mapping(repository, previous, mapping, measured['proposed_normal_deadline_seconds'])
        # Fresh task-profile conformance is checked independently before invocation.
        # Neither old permissions nor old identity evidence authorizes this plan.
        ignored.add('differential_conformance_digest')
    if (prior_environment.model_dump(exclude=ignored) != current_environment.model_dump(exclude=ignored)
            or (not calibrated and any((current_environment.conformance_digests or {}).get(key) != value
                   for key, value in (prior_environment.conformance_digests or {}).items()))):
        raise ConfigurationError('pilot workers or environment policy changed; collect fresh timing')
    return previous
