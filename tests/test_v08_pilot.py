from __future__ import annotations

import pytest
from pydantic import ValidationError
from test_v08_assessment import setup_assessment

from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentPlan,
    PilotPolicy,
    content_digest,
)
from aeep.assessment.pilot import require_separation, timing_preview
from aeep.errors import ConfigurationError

pytestmark = pytest.mark.assessment_lifecycle


async def test_pilot_uses_campaign_but_cannot_qualify_or_reuse_holdout(tmp_path, monkeypatch):
    router, service, original, grant = setup_assessment(tmp_path)
    try:
        assert 'pilot' not in original.model_dump()
        with pytest.raises(ValidationError):
            PilotPolicy(deadline_multiplier=float('inf'))
        with pytest.raises(ValidationError):
            PilotPolicy(minimum_deadline_seconds=20, maximum_deadline_seconds=10)
        pilot = service.propose(subject_id=original.subject_digest, family='csv',
            candidate_id=original.candidate_id, baseline_id=original.baseline_id,
            authorization_id=grant.authorization_id,
            environment=AssessmentEnvironment.model_validate(service.repository.get('environment',original.environment_digest)),
            seed=123, pilot=PilotPolicy())
        assert pilot.schema_version == 'assessment.plan.v5'
        assert len(pilot.suite.cases) == 8 and not pilot.suite.stop_on_screening_failure
        for digest in pilot.definition_digests:
            service.repository.review(digest)
        before = service.budget_preview(pilot.plan_id)['remaining']
        report = await service.run(service.enqueue(pilot.plan_id))
        assert not report.qualification_passed and report.outcome == 'insufficient_evidence'
        with pytest.raises(ConfigurationError, match='admission requires'):
            service.admit(report.report_id)
        measured = timing_preview(service, report.report_id)
        assert measured['complete_measurements'] and measured['assigned_executions'] == 16
        assert measured['proposed_normal_deadline_seconds'] >= 1
        assert not measured['authorization_changed']
        assert measured['remaining']['elapsed_seconds'] < before['elapsed_seconds']
        with pytest.raises(ValidationError, match='eight distinct'):
            AssessmentPlan.model_validate({**pilot.model_dump(), 'suite': original.suite.model_dump()})
        altered = original.model_copy(deep=True)
        altered.suite.cases[-1].action.input = pilot.suite.cases[0].action.input
        with pytest.raises(ConfigurationError, match='cannot enter'):
            require_separation(service.repository, altered)
        changed = pilot.model_copy(deep=True)
        changed.suite.cases[0].action.input = original.suite.cases[-1].action.input
        with pytest.raises(ConfigurationError, match='cannot enter'):
            require_separation(service.repository, changed)
        assert content_digest(pilot) == content_digest(service.repository.get('plan',pilot.plan_id))
        with pytest.raises(ValidationError, match='main plan'):
            AssessmentPlan.model_validate({**pilot.model_dump(), 'schema_version':'assessment.plan.v6'})
        main = service.propose(subject_id=original.subject_digest, family='csv',
            candidate_id=original.candidate_id, baseline_id=original.baseline_id,
            authorization_id=grant.authorization_id,
            environment=AssessmentEnvironment.model_validate(service.repository.get('environment',original.environment_digest)),
            seed=456, pilot_report_id=report.report_id)
        assert main.pilot is None and main.pilot_report_digest == content_digest(report)
        assert main.schema_version == 'assessment.plan.v6' and len(main.suite.cases) == 141
        assert pilot.plan_id in main.preparation_request_ids
        from aeep.assessment.pilot import require_linked_pilot
        read_mapping = service.repository.get
        def corrupted_mapping(kind, identity):
            value = read_mapping(kind, identity)
            if kind == 'mapping' and identity == main.mapping_digest:
                value['candidate']['description'] = 'altered after review'
            return value
        with monkeypatch.context() as patch:
            patch.setattr(service.repository, 'get', corrupted_mapping)
            with pytest.raises(ConfigurationError, match='main mapping identity differs'):
                require_linked_pilot(service.repository, main)
        mismatched = main.model_copy(update={'baseline_id':'different'})
        with pytest.raises(ConfigurationError,match='pilot evidence differs'):
            require_linked_pilot(service.repository, mismatched)
        additional = AssessmentEnvironment.model_validate(service.repository.get('environment',main.environment_digest))
        additional.conformance_digests = {'extra_challenger':'a'*64}
        added_digest = service.repository.put('environment','additional-cost-profile',additional)
        # This verifies lineage only, not the added profile's execution eligibility.
        assert require_linked_pilot(service.repository,main.model_copy(update={'environment_digest':added_digest})) == pilot
        read = service.repository.get
        def prior_boundary(kind, identity):
            value = read(kind, identity)
            return {**value, 'conformance_digests': {'candidate':'b'*64}} if kind == 'environment' and identity == pilot.environment_digest else value
        with monkeypatch.context() as patch:
            patch.setattr(service.repository, 'get', prior_boundary)
            with pytest.raises(ConfigurationError,match='environment policy changed'):
                require_linked_pilot(service.repository,main.model_copy(update={'schema_version':'assessment.plan.v5','environment_digest':added_digest}))
            assert require_linked_pilot(service.repository, main.model_copy(update={'environment_digest':added_digest})) == pilot
            retained = additional.model_copy(update={'conformance_digests':{'candidate':'b'*64,'extra_challenger':'a'*64}})
            retained_digest = service.repository.put('environment','retained-cost-profile',retained)
            assert require_linked_pilot(service.repository,main.model_copy(update={'environment_digest':retained_digest})) == pilot
        additional.network = True
        changed_digest = service.repository.put('environment','changed-cost-policy',additional)
        with pytest.raises(ConfigurationError,match='environment policy changed'):
            require_linked_pilot(service.repository,main.model_copy(update={'environment_digest':changed_digest}))
        for digest in main.definition_digests:
            service.repository.review(digest)
        # The prior operations are included, never debited a second time.
        prior_ids = {item.operation_id for item in service.repository.operation_ledger(pilot.plan_id).operations}
        main_report = await service.run(service.enqueue(main.plan_id))
        ledger = service.repository.get('operation_ledger', main_report.operation_ledger_digest)
        ids = [item['operation_id'] for item in ledger['operations']]
        assert prior_ids <= set(ids) and len(ids) == len(set(ids))
        assert main_report.measured_usage['known_overhead_wall_time_ms'] >= report.measured_usage['known_campaign_wall_time_ms']
        assert main_report.distinct_holdout_cases == 105
        get = service.repository.get
        from aeep.benchmarking import BenchmarkCampaignReport
        campaign = BenchmarkCampaignReport.model_validate(get('campaign', report.campaign_digest))
        for fault in ('missing', 'duplicate', 'incorrect', 'too_slow'):
            modified = campaign.model_copy(deep=True)
            if fault == 'missing':
                modified.trials[0].wall_time_ms = None
            elif fault == 'duplicate':
                modified.trials.append(modified.trials[0])
            elif fault == 'incorrect':
                modified.trials[0].valid = False
            else:
                for trial in modified.trials:
                    trial.wall_time_ms = 1_000_000
            updated = report.model_copy(update={'campaign_digest': content_digest(modified)})
            def simulated(kind, identity, updated=updated, modified=modified):
                if kind == 'report':
                    return updated.model_dump(mode='json')
                if kind == 'campaign':
                    return modified.model_dump(mode='json')
                return get(kind, identity)
            with monkeypatch.context() as patch:
                patch.setattr(service.repository, 'get', simulated)
                result = timing_preview(service, report.report_id)
                if fault == 'missing':
                    with pytest.raises(ConfigurationError, match='bounded deadline'):
                        require_linked_pilot(service.repository, main.model_copy(update={
                            'pilot_report_digest':content_digest(updated),
                            'definition_digests':[*main.definition_digests, content_digest(updated)]}))
                if fault == 'incorrect':
                    assert result['complete_measurements']
                    assert result['proposed_normal_deadline_seconds'] is not None
                else:
                    assert result['proposed_normal_deadline_seconds'] is None
        duplicate = pilot.model_dump()
        duplicate['suite']['cases'][1]['action']['input'] = duplicate['suite']['cases'][0]['action']['input']
        with pytest.raises(ValidationError, match='eight distinct'):
            AssessmentPlan.model_validate(duplicate)
    finally:
        await router.close()


async def test_managed_calibration_rejects_every_change_except_measured_timeout(tmp_path, monkeypatch):
    from test_v08_pair_inspection import definition

    from aeep.assessment.models import ReviewedMapping
    from aeep.assessment.pilot import _require_calibrated_mapping

    router, service, original, _ = setup_assessment(tmp_path)
    pair = definition(task_profile=True)
    previous = ReviewedMapping(candidate=pair.treatment, baseline=pair.control)
    digest = service.repository.put('mapping', 'managed-pilot', previous)
    pilot = original.model_copy(update={'mapping_digest':digest,
        'candidate_id':pair.treatment.id, 'baseline_id':pair.control.id})
    try:
        calibrated = previous.model_copy(deep=True)
        for spec in calibrated.subjects:
            spec.config['timeout_seconds'] = 203
        _require_calibrated_mapping(service.repository, pilot, calibrated, 203)
        assert previous.candidate.config['timeout_seconds'] == 60
        for key, value in (
            ('timeout_seconds', 204), ('model', 'different'),
            ('instructions', 'different task'), ('adapter_id', 'codex-exec'),
            ('managed_worker', {**pair.treatment.config['managed_worker'], 'image':'sha256:'+'f'*64}),
            ('invocation', {**pair.treatment.config['invocation'], 'exposure':'required'}),
        ):
            changed = calibrated.model_copy(deep=True)
            changed.candidate.config[key] = value
            with pytest.raises(ConfigurationError, match='only its measured'):
                _require_calibrated_mapping(service.repository, pilot, changed, 203)
        with pytest.raises(ConfigurationError, match='only its measured'):
            _require_calibrated_mapping(service.repository, pilot, calibrated, None)
        removed = calibrated.model_copy(deep=True)
        removed.candidate.id = 'different'
        with pytest.raises(ConfigurationError, match='cannot remove'):
            _require_calibrated_mapping(service.repository, pilot, removed, 203)
        duplicate = calibrated.model_copy(deep=True)
        duplicate.dependencies.append(previous.candidate)
        with pytest.raises(ConfigurationError, match='distinct implementation IDs'):
            _require_calibrated_mapping(service.repository, pilot, duplicate, 203)
        for timeout in (True, float('inf'), -1):
            invalid = calibrated.model_copy(deep=True)
            invalid.candidate.config['timeout_seconds'] = timeout
            with pytest.raises(ConfigurationError, match='only its measured'):
                _require_calibrated_mapping(service.repository, pilot, invalid, 1)
        read_mapping = service.repository.get
        def corrupted_mapping(kind, identity):
            value = read_mapping(kind, identity)
            if kind == 'mapping':
                value['candidate']['description'] = 'altered after review'
            return value
        monkeypatch.setattr(service.repository, 'get', corrupted_mapping)
        with pytest.raises(ConfigurationError, match='pilot mapping identity differs'):
            _require_calibrated_mapping(service.repository, pilot, calibrated, 203)
    finally:
        await router.close()


async def test_calibrated_main_executes_without_recharging_pilot(tmp_path):
    router, service, original, grant = setup_assessment(tmp_path)
    environment = AssessmentEnvironment.model_validate(service.repository.get('environment', original.environment_digest))
    options = dict(subject_id=original.subject_digest, family='csv',
        candidate_id=original.candidate_id, baseline_id=original.baseline_id,
        authorization_id=grant.authorization_id, environment=environment)
    try:
        pilot = service.propose(**options, seed=123, pilot=PilotPolicy())
        for digest in pilot.definition_digests:
            service.repository.review(digest)
        report = await service.run(service.enqueue(pilot.plan_id))
        timing = timing_preview(service, report.report_id)
        prior_ledger = service.repository.operation_ledger(pilot.plan_id)
        for spec in router.manifest.executors:
            spec.config['timeout_seconds'] = timing['proposed_normal_deadline_seconds']
            router.registry.replace(spec)
        with pytest.raises(ConfigurationError, match='route changed'):
            timing_preview(service, report.report_id)
        main = service.propose(**options, seed=456, pilot_report_id=report.report_id)
        assert main.schema_version == 'assessment.plan.v6' and not main.blocked_reasons
        with pytest.raises(ConfigurationError, match='review'):
            service.enqueue(main.plan_id)
        for digest in main.definition_digests:
            service.repository.review(digest)
        result = await service.run(service.enqueue(main.plan_id))
        assert result.distinct_holdout_cases == 105 and result.qualification_passed
        assert service.repository.operation_ledger(pilot.plan_id) == prior_ledger
        all_costs = service.repository.get('operation_ledger', result.operation_ledger_digest)
        ids = [item['operation_id'] for item in all_costs['operations']]
        assert len(ids) == len(set(ids))
        assert {item.operation_id for item in prior_ledger.operations} <= set(ids)
        assert content_digest(pilot) == content_digest(service.repository.get('plan', pilot.plan_id))
    finally:
        await router.close()
