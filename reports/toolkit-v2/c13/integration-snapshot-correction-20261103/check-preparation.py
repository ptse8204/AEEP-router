"""First-party controls only. No Docker, upstream SDK, credentials or model calls."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
from datetime import timedelta
from pathlib import Path

import integration as prepare
import run

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, content_digest
from aeep.models import Manifest, SubscriptionResource, utc_now
from aeep.router import Router


async def main():
    controls = []
    pair, _shared = prepare.pair('sha256:' + 'e' * 64)
    rec = prepare.recipe()
    assert len(rec.generator_config['cases']) == 3
    assert len(rec.extension.independent_fixtures) == 2
    assert len(rec.extension.transformed_fixtures) == 1
    assert all(case['used_for_development'] for case in rec.generator_config['cases'])
    controls.append('three existing independent calibration cases, one selected model task')
    assert pair.control.config['managed_worker']['image'] == prepare.PARENT_ID
    assert pair.treatment.config['managed_worker']['image'] != prepare.PARENT_ID
    assert not any('ponytail' in path for path in pair.treatment.config['managed_worker']['reviewed_files'])
    assert pair.control.config['invocation']['mode'] == 'turn'
    assert pair.treatment.config['invocation']['exposure'] == 'required'
    assert pair.control.config['instructions'] == pair.treatment.config['instructions']
    assert 'Current task JSON and bound artifact paths:\n{input}' in pair.control.config['instructions']
    controls.append('neutral reviewed skill and capable shared profile remain exact')
    scheduler = prepare.scheduler()
    assert scheduler.maximum_requests == 1
    assert scheduler.source_revision == prepare.ASE_REVISION
    assert scheduler.executor.config['env']['PATH'].split(':')[0] == str(prepare.TOOLS)
    assert not prepare.SCHEDULER_WORK.exists()
    controls.append('one-request scheduler binds actual retained runtime and owned Git helper')
    captured = {}
    projections = []
    old_emit, old_service_check = run.emit, None
    run.emit = lambda name, value: captured.setdefault(name, value)
    try:
        with tempfile.TemporaryDirectory(prefix='aeep-engineering-definition-fixture-') as temporary:
            root = Path(temporary)
            manifest_path = root / 'manifest.json'
            manifest_path.write_text(Manifest(database=str(root / 'fixture.sqlite3'),
                executors=[pair.control, pair.treatment],
                resources=[SubscriptionResource(id='codex.self', provider='openai', product='codex')]).model_dump_json())
            router = Router.from_manifest(manifest_path)
            service = run.AssessmentService(router, root / 'assessments')
            repo = service.repository
            try:
                subject = service.inspect_local(prepare.CANDIDATE, kind='skill')
                # This grant belongs only to the explicitly synthetic temporary
                # fixture. It is not copied from or usable by the real grant.
                repo.grant(AssessmentAuthorization(authorization_id='onboarding',
                    subject_digests=[content_digest(subject)], recipe_digests=[content_digest(rec)],
                    environment_digests=['f' * 64], limits=AssessmentLimits(
                        max_operations=1000, max_model_turns=2, max_elapsed_seconds=20000),
                    expires_at=utc_now() + timedelta(hours=1)))
                requests = run.prepare_inspection(service, pair, rec, subject)
                assert len(requests) == 2
                controls.append('prepared inspection definitions and scope use one existing selected grant identity')
                boundary = {'boundaries': {role: {'conformance_digest': str(i) * 64}
                    for i, role in enumerate(('control', 'treatment'), 1)},
                    'differential_conformance_digest': '3' * 64}
                # No actual conformance claim is minted. Skip only the final
                # execution-readiness call in this pure construction fixture.
                service._verify_dependencies = lambda plan: None
                plans = []
                for engine in ('agent-skill-eval', 'managed'):
                    plan, review_ref = run.prepare_plan(service, pair, rec, subject, boundary, engine)
                    assert len(plan.suite.routes) == len(plan.suite.cases) == 1
                    assert plan.suite.cases[0].case_id == prepare.load(prepare.HERE / 'task.json')['input']['task_id']
                    assert plan.scheduler_digest is not None if engine == 'agent-skill-eval' else plan.scheduler_digest is None
                    assert not plan.blocked_reasons
                    projection = service.budget_preview(plan.plan_id)['campaign_allowance']
                    projections.append({'engine': engine, 'upper_allowance': projection['upper_allowance'],
                        'gaps_in_synthetic_fixture': projection['gaps']})
                    plans.append(plan)
                controls.append('both frozen engine plans retain one required-use task without challenger or fallback')
                assert plans[0].plan_id != plans[1].plan_id
                assert [tuple(repo.store._connection.execute(
                    "SELECT operations,model_turns FROM assessment_grants WHERE id='onboarding'").fetchone())] == [(0, 0)]
                controls.append('pure construction starts no operation or model turn')
            finally:
                await router.close()
    finally:
        run.emit = old_emit
    output = {'passed': True, 'controls': controls, 'fixture_only': True,
        'actual_upstream_or_workers_executed': False, 'actual_grant_touched': False,
        'actual_conformance_created': False, 'candidate_or_selection_value': 'NOT_ASSESSED',
        'inert_campaign_projections': projections}
    prepare.write(prepare.HERE / 'preparation-controls.json', output)
    print(json.dumps(output))


if __name__ == '__main__':
    asyncio.run(main())
