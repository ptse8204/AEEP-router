from __future__ import annotations

import json
import sqlite3
import sys
from datetime import timedelta

import pytest
from conftest import manifest_with, python_spec
from typer.testing import CliRunner

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits
from aeep.assessment.recipes import shipped_recipe
from aeep.cli import app
from aeep.models import utc_now

pytestmark = pytest.mark.assessment_lifecycle


async def test_completed_worker_exit_preserves_admission_when_reading_report(tmp_path, monkeypatch):
    import asyncio
    import os
    import subprocess
    import sys
    from pathlib import Path

    from test_v08_assessment import setup_assessment

    from aeep.assessment import recovery
    from aeep.assessment.service import AssessmentService
    from aeep.mcp.server import AEEPToolService
    from aeep.models import ActionRequest
    from aeep.router import Router

    source, assessment, plan, _grant = setup_assessment(tmp_path)
    manifest = source.manifest.model_copy(deep=True)
    manifest.database = str(tmp_path / "worker-exit.db")
    manifest_file = tmp_path / "aeep.json"
    manifest_file.write_text(manifest.model_dump_json())
    identity = assessment.enqueue(plan.plan_id)
    with sqlite3.connect(manifest.database) as destination:
        source.store._connection.backup(destination)
    await source.close()
    root = (await asyncio.to_thread(Path(__file__).resolve)).parents[1]
    # This runs the full frozen assessment, not just process startup. Hosted
    # Windows filesystem checks can take several minutes. subprocess.run owns
    # termination and pipe cleanup if the finite harness deadline is exceeded.
    process = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "aeep.assessment.worker", "--manifest", str(manifest_file),
         "--directory", str(assessment.directory), "--assessment", identity],
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(root / "src"), str(root / "tests")])},
        capture_output=True, timeout=900, check=False,
    )
    assert process.returncode == 0, process.stderr.decode()
    router = Router.from_manifest(manifest_file)
    try:
        assessment = AssessmentService(router, assessment.directory)
        assert recovery.worker_alive(assessment.repository, identity) is False
        job = assessment.status(identity)
        assert job["state"] == "complete"
        admission = assessment.admit(job["report_id"])
        tools = AEEPToolService(router, profile="assessment")
        for operation in ("status", "report"):
            result = await tools.call("aeep_assessment_" + operation, {"assessment_id": identity})
            assert not result["isError"]
        request = ActionRequest(capability=plan.suite.domain, input=plan.suite.cases[0].action.input)
        assert any(candidate.executor_id == admission.executor_id and candidate.feasible
                   for candidate in router.route(request).candidates)
        for state in ("queued", "cancelled", "indeterminate"):
            with router.store._immediate_transaction() as connection:
                connection.execute("UPDATE assessment_jobs SET state=? WHERE id=?", (state, identity))
            assert assessment.status(identity)["state"] == state
            assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 0
        # A worker may finish after the liveness check but before recovery locks the job.
        def finished_during_check(_repository, _identity):
            with router.store._immediate_transaction() as connection:
                connection.execute("UPDATE assessment_jobs SET state='complete' WHERE id=?", (identity,))
            return False

        with router.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_jobs SET state='running' WHERE id=?", (identity,))
        with monkeypatch.context() as patch:
            patch.setattr(recovery, "worker_alive", finished_during_check)
            assert assessment.status(identity)["state"] == "complete"
        assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 0
        with router.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_jobs SET state='running' WHERE id=?", (identity,))
        assert assessment.status(identity)["error_code"] == "worker_disappeared"
        assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 1
        assert router.route(request).selected_executor_id == plan.baseline_id
    finally:
        await router.close()


async def test_model_job_controls_launch_only_the_configured_worker(tmp_path, monkeypatch):
    from test_v08_assessment import setup_assessment

    from aeep.assessment import tools, worker
    from aeep.mcp.server import AEEPToolService
    from aeep.router import Router

    source, assessment, plan, _grant = setup_assessment(tmp_path, operations=1)
    manifest = source.manifest.model_copy(deep=True)
    manifest.database = str(tmp_path / "persistent.db")
    manifest_file = tmp_path / "aeep.json"
    manifest_file.write_text(manifest.model_dump_json())
    with sqlite3.connect(manifest.database) as destination:
        source.store._connection.backup(destination)
    await source.close()
    launched = []

    class Process:
        def poll(self):
            return None

    def launch(argv, **kwargs):
        launched.append((argv, kwargs))
        return Process()

    monkeypatch.setattr(tools.subprocess, "Popen", launch)
    router = Router.from_manifest(manifest_file)
    service = AEEPToolService(router, profile="assessment")
    try:
        started = await service.call("aeep_assessment_start", {"plan_id": plan.plan_id})
        assert not started["isError"]
        identity = started["structuredContent"]["assessment_id"]
        assert launched[0][0][1:3] == ["-m", "aeep.assessment.worker"]
        assert str(manifest_file) in launched[0][0]
        assert "auth" not in " ".join(launched[0][0])
        await worker.run(manifest_file, assessment.directory, identity)
        status = await service.call("aeep_assessment_status", {"assessment_id": identity})
        assert status["structuredContent"]["state"] == "complete"
        report = await service.call("aeep_assessment_report", {"assessment_id": identity})
        assert report["structuredContent"]["outcome"] == "insufficient_evidence"
        assert not (await service.call("aeep_assessment_cancel", {"assessment_id": identity}))[
            "isError"
        ]
        again = await service.call("aeep_assessment_start", {"plan_id": plan.plan_id})
        assert again["structuredContent"]["assessment_id"] == identity
        assert len(launched) == 1
    finally:
        await router.close()


def test_operator_cli_keeps_review_and_authorization_separate(tmp_path):
    recipe = shipped_recipe("csv")
    specs = [
        python_spec(
            name,
            "aeep.assessment.recipes:reference_csv",
            capability=recipe.capability,
            input_schema=recipe.input_schema,
            output_schema=recipe.output_schema,
        )
        for name in ["candidate", "baseline"]
    ]
    manifest = manifest_with(*specs)
    manifest.database = str(tmp_path / "state.db")
    path = tmp_path / "aeep.json"
    path.write_text(manifest.model_dump_json())
    plugin = tmp_path / "plugin.txt"
    plugin.write_text("local test plugin")
    environment = tmp_path / "environment.json"
    environment.write_text(
        json.dumps(
            {
                "environment_id": "fixture",
                "kind": "trusted_local",
                "identity": {"runtime": "fixture"},
            }
        )
    )
    runner = CliRunner()

    def invoke(*arguments):
        result = runner.invoke(app, ["assess", "-m", str(path), *arguments])
        assert result.exit_code == 0, result.exception or result.output
        return json.loads(result.stdout)

    subject = invoke("inspect", str(plugin))
    assert invoke("inspect", str(plugin))["subject_id"] == subject["subject_id"]
    plan = invoke(
        "propose", subject["subject_id"], "csv", "candidate", "baseline", "grant", str(environment)
    )
    assert invoke("show", "plan", plan["plan_id"])["plan_id"] == plan["plan_id"]
    for digest in plan["definition_digests"]:
        assert invoke("review", digest)["reviewed"]
    grant = AssessmentAuthorization(
        authorization_id="grant",
        subject_digests=[plan["subject_digest"]],
        recipe_digests=[plan["recipe_digest"]],
        environment_digests=[plan["environment_digest"]],
        limits=AssessmentLimits(max_operations=1, max_elapsed_seconds=200),
        expires_at=utc_now() + timedelta(hours=1),
    )
    grant_file = tmp_path / "grant.json"
    grant_file.write_text(grant.model_dump_json())
    assert invoke("authorize", str(grant_file))["authorization_id"] == "grant"
    assert invoke('setup-options', 'grant')['items']
    proposed = invoke('setup', subject['subject_id'], plan['recipe_digest'], 'candidate', 'baseline',
                      'grant', plan['environment_digest'])
    assert proposed['status'] == 'plan_review_required' and not proposed['execution_authorized']
    report = invoke("run", plan["plan_id"])
    assert report["outcome"] == "insufficient_evidence"
    import asyncio

    from aeep.router import Router

    router = Router.from_manifest(path)
    job = router.store._connection.execute("SELECT id FROM assessment_jobs").fetchone()[0]
    asyncio.run(router.close())
    assert invoke("status", job)["state"] == "complete"
    assert invoke("report", job)["report_id"] == report["report_id"]
    assert invoke("cancel", job)["state"] == "complete"
    recipe_file = tmp_path / "recipe.json"
    recipe_file.write_text(recipe.model_dump_json())
    assert invoke("define", str(recipe_file))["reviewed"] is False
    assert invoke("revoke", "grant")["revoked"]


def test_product_verifier_never_promotes_offline_checks_to_live_completion(tmp_path, monkeypatch):
    from aeep.assessment import verification

    monkeypatch.setattr(verification, "_pytest", lambda *_args: (True, ""))
    report = verification.verify_assessment_product(tmp_path)
    assert report.offline_checks_passed
    assert not report.complete_economic_accounting
    assert not report.live_codex_verified and not report.release_ready
    assert report.remaining_gates
    assert report.schema_version == 'assessment.verification.v2'
    assert report.adoption_gates['explanation_accuracy'] == 'offline-only'
    assert report.adoption_gates['human_usability'] == 'not-yet-measured'
    assert report.adoption_gates['resource_acceptance'] == 'not-yet-measured'
    result = CliRunner().invoke(app, ["verify", "assessment-product", "--strict"])
    assert result.exit_code == 1
    assert not json.loads(result.stdout)["release_ready"]
    monkeypatch.setattr(verification, "_pytest", lambda *_args: (False, "fixture failure"))
    assert verification.verify_assessment_product(tmp_path).failure_detail == "fixture failure"


def test_release_verifier_uses_records_and_commands_not_success_flags(tmp_path, monkeypatch):
    from aeep.assessment import verification

    monkeypatch.setattr(verification, "_pytest", lambda *_args: (True, ""))
    monkeypatch.setattr(verification, "verify_compatibility", lambda _root: (True, ""))
    monkeypatch.setattr(verification, "verify_live_records", lambda *_args: {"host_verified": False, "campaigns_verified": True, "capability_calls_verified": True, "admitted_execution_observed": True, "demonstrated_savings": False})
    result = verification.verify_assessment_product(tmp_path, manifest=tmp_path / "selected.json", release_checks=True)
    assert result.live_codex_verified and result.compatibility_checks_passed
    assert not result.host_inventory_and_invocation and not result.release_ready
    assert not result.demonstrated_savings
    assert "live verification of Codex inventory and effective tool isolation" in result.remaining_gates


def test_release_commands_stop_on_failure_and_detect_source_drift(tmp_path, monkeypatch):
    import subprocess

    from aeep.assessment import verification

    calls = []

    def successful(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", successful)
    assert verification.verify_compatibility(tmp_path) == (True, "")
    assert any("coverage" in command for command in calls)
    assert any(command[0] == "npm" for command in calls)
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "failed check", ""))
    assert not verification.verify_compatibility(tmp_path)[0]
    def unavailable(*args, **kwargs):
        raise OSError("missing runtime")
    monkeypatch.setattr(subprocess, "run", unavailable)
    assert not verification.verify_compatibility(tmp_path)[0]
    monkeypatch.setattr(subprocess, "run", successful)
    digests = iter(["before", "after"])
    monkeypatch.setattr(verification, "verification_source_digest", lambda root: next(digests))
    assert not verification.verify_compatibility(tmp_path)[0]


async def test_live_record_verifier_rejects_offline_or_changed_evidence(tmp_path, monkeypatch):
    import asyncio
    from pathlib import Path

    from test_v08_assessment import setup_assessment

    from aeep.assessment.verification import verify_live_records

    router, service, plan, _grant = setup_assessment(tmp_path, operations=1)
    try:
        assessment_id = service.enqueue(plan.plan_id)
        await service.run(assessment_id)
        manifest = router.manifest.model_copy(deep=True)
        manifest.database = str(tmp_path / "evidence.sqlite3")
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(manifest.model_dump_json())
        with sqlite3.connect(manifest.database) as target:
            router.store._connection.backup(target)
        result = await asyncio.to_thread(verify_live_records, Path(__file__).parents[1], manifest_file, [assessment_id], ["missing-receipt"])
        assert not result["host_verified"] and not result["campaigns_verified"]
        assert not result["admitted_execution_observed"]
        assert result["details"]
    finally:
        await router.close()


@pytest.mark.parametrize('family', ['csv', 'text', 'search'])
async def test_configured_setup_preserves_scope_choice_and_budget(tmp_path, family):
    from test_v08_assessment import setup_assessment

    from aeep.assessment.models import AssessmentSetupRequest, content_digest
    from aeep.assessment.onboarding import prepare_setup, setup_options
    from aeep.errors import ConfigurationError

    router, service, original, _grant = setup_assessment(tmp_path, family)
    try:
        before = tuple(router.store._connection.execute('SELECT * FROM assessment_grants').fetchone())
        request = AssessmentSetupRequest(authorization_id=original.authorization_id, subject_id=original.subject_digest,
            recipe_id=original.recipe_digest, environment_id=original.environment_digest,
            candidate_id=original.candidate_id, baseline_id=original.baseline_id, structure='workflow', seed=42)
        first = prepare_setup(service, request)
        assert first['status'] == 'plan_review_required' and not first['execution_authorized']
        assert first['structure_choices']['selected'] == 'workflow'
        with pytest.raises(ConfigurationError, match='distinct implementations'):
            prepare_setup(service, request.model_copy(update={'candidate_id': request.baseline_id}))
        # The stored choice remains the default for this subject/capability/environment.
        again = prepare_setup(service, request.model_copy(update={'structure': None, 'seed': 43}))
        assert again['structure_choices']['selected'] == 'workflow'
        assert again['plan_id'] != first['plan_id']
        assert tuple(router.store._connection.execute('SELECT * FROM assessment_grants').fetchone()) == before
        assert not router.store.list_receipts()
        pages, after = [], ''
        while True:
            page = setup_options(service, original.authorization_id, after=after, limit=1)
            pages.extend(page['items'])
            after = page['next_cursor']
            if after is None:
                break
        assert len({(item['kind'], item['id']) for item in pages}) == len(pages) == 5
        assert str(tmp_path) not in json.dumps(pages)
        other = shipped_recipe('text' if family != 'text' else 'csv')
        digest = service.repository.put('recipe', content_digest(other), other)
        with pytest.raises(ConfigurationError, match='authorization scope'):
            prepare_setup(service, request.model_copy(update={'recipe_id': digest}))
        with pytest.raises(ConfigurationError, match='bounds'):
            setup_options(service, original.authorization_id, limit=51)
        service.repository.revoke(original.authorization_id)
        for callback in (lambda: prepare_setup(service, request), lambda: setup_options(service, original.authorization_id)):
            with pytest.raises(ConfigurationError, match='revoked'):
                callback()
    finally:
        await router.close()


async def test_model_setup_generates_reviewed_fixtures_without_revealing_answers(tmp_path, monkeypatch):
    from test_v08_executable_recipes import setup

    from aeep.assessment.models import AssessmentSetupRequest
    from aeep.assessment.service import AssessmentService
    from aeep.mcp.server import AEEPToolService
    from aeep.router import Router

    source, _service, _recipe, original, _environment = setup(tmp_path, monkeypatch)
    manifest = source.manifest.model_copy(deep=True)
    manifest.database = str(tmp_path / 'persistent.db')
    path = tmp_path / 'aeep.json'
    path.write_text(manifest.model_dump_json())
    with sqlite3.connect(manifest.database) as destination:
        source.store._connection.backup(destination)
    await source.close()
    router = Router.from_manifest(path)
    assessment = AssessmentService(router, tmp_path / '.aeep/assessments')
    tool = AEEPToolService(router, profile='assessment')
    request = AssessmentSetupRequest(authorization_id=original.authorization_id, subject_id=original.subject_digest,
        recipe_id=original.recipe_digest, environment_id=original.environment_digest,
        candidate_id='candidate', baseline_id='baseline', seed=42)
    try:
        options = await tool.call('aeep_assessment_options', {'authorization_id': original.authorization_id})
        assert not options['isError']
        first = (await tool.call('aeep_assessment_setup', request.model_dump(mode='json')))['structuredContent']
        assert first['status'] == 'recipe_review_required'
        assert first['generation_allowance']['max_model_turns'] == 0
        arguments = {'materialization_id': first['materialization_id']}
        denied = await tool.call('aeep_assessment_generate_cases', arguments)
        assert denied['isError']
        assert router.store._connection.execute('SELECT count(*) FROM assessment_operations').fetchone()[0] == 0
        # Only the operator can review the exact recipe/runtime definitions.
        for digest in first['definition_digests']:
            assessment.repository.review(digest)
        generated = await tool.call('aeep_assessment_generate_cases', arguments)
        assert not generated['isError']
        assert set(generated['structuredContent']) == {'case_set_id', 'case_count', 'recipe_digest'}
        assert generated['structuredContent']['case_count'] == 141
        before = tuple(router.store._connection.execute('SELECT * FROM assessment_grants').fetchone())
        assert (await tool.call('aeep_assessment_generate_cases', arguments)) == generated
        assert tuple(router.store._connection.execute('SELECT * FROM assessment_grants').fetchone()) == before
        final = (await tool.call('aeep_assessment_setup', first['next_setup_arguments']))['structuredContent']
        assert final['status'] == 'plan_review_required'
        assert final['budget']['minimum_trial_model_turns'] == 0
        assert (await tool.call('aeep_assessment_start', {'plan_id': final['plan_id']}))['isError']
        for extra in ({'approved': True}, {'max_model_turns': 10000}, {'environment': {'kind': 'trusted_local'}}):
            assert (await tool.call('aeep_assessment_setup', {**request.model_dump(mode='json'), **extra}))['isError']
        assert not router.store.list_receipts()
    finally:
        await router.close()


async def test_workbook_setup_prepares_current_recipe_without_running_it(tmp_path, monkeypatch):
    from test_v08_executable_recipes import setup

    from aeep.assessment.models import AssessmentSetupRequest
    from aeep.assessment.onboarding import prepare_setup
    from aeep.assessment.workbook import workbook_recipe

    router, service, recipe, original, _environment = setup(tmp_path, monkeypatch, recipe=workbook_recipe())
    try:
        for spec in router.registry.all():
            spec.capability = recipe.capability
        request = AssessmentSetupRequest(authorization_id=original.authorization_id, subject_id=original.subject_digest,
            recipe_id=original.recipe_digest, environment_id=original.environment_digest,
            candidate_id='candidate', baseline_id='baseline')
        result = prepare_setup(service, request)
        assert result['status'] == 'recipe_review_required'
        assert result['next_setup_arguments']['recipe_id'] == original.recipe_digest
        assert result['generation_allowance']['max_elapsed_seconds'] == 35
        assert router.store._connection.execute('SELECT count(*) FROM assessment_operations').fetchone()[0] == 0
    finally:
        await router.close()


async def test_agent_setup_requires_reviewed_experiment_and_matching_capable_workers(tmp_path):
    from test_v08_assessment import setup_assessment
    from test_v08_incremental import environment
    from test_v08_managed_workers import binding

    from aeep.assessment.models import (
        AssessmentSetupRequest,
        IncrementalExperiment,
        UtilityPolicy,
        content_digest,
    )
    from aeep.assessment.onboarding import incremental_host_routes, prepare_setup
    from aeep.errors import ConfigurationError
    from aeep.hosts.base import HostModel
    from aeep.models import ManagedHostInvocation

    router, service, original, _grant = setup_assessment(tmp_path)
    try:
        subject = service.repository.get('subject', original.subject_digest)
        skill_digest = next(iter(subject['dependency_digests'].values()))
        control = binding().model_copy(update={'worker_id': 'control'})
        routes = incremental_host_routes(recipe=shipped_recipe('csv'), control_worker=control,
            treatment_worker=control.model_copy(update={'worker_id': 'treatment'}),
            higher_worker=control.model_copy(update={'worker_id': 'higher'}),
            reusable_worker=control.model_copy(update={'worker_id': 'reusable'}),
            candidate_invocation=ManagedHostInvocation(mode='skill', skill_name='fixture',
                skill_path='/opt/plugin/SKILL.md', skill_sha256=skill_digest),
            model=HostModel(id='observed-model', reasoning_efforts=('low', 'medium')),
            normal_effort='low', effort_order=('low', 'medium'), timeout_seconds=30, protocol_user_agent='fixture')
        routes[1].config['invocation']['exposure'] = 'required'
        for spec in routes:
            router.registry.register(spec)
        request = AssessmentSetupRequest(authorization_id=original.authorization_id, subject_id=original.subject_digest,
            recipe_id=original.recipe_digest, environment_id=original.environment_digest,
            candidate_id=routes[1].id, baseline_id=routes[0].id, structure='workflow')
        with pytest.raises(ConfigurationError, match='reviewed incremental experiment'):
            prepare_setup(service, request)
        experiment = IncrementalExperiment(stage='qualification', exposure='required', environment=environment(),
            utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'], guardrail_dimensions=['wall_time_ms']))
        digest = service.repository.put('experiment', content_digest(experiment), experiment)
        request.experiment_id = digest
        with pytest.raises(ConfigurationError, match='operator-reviewed experiment'):
            prepare_setup(service, request)
        service.repository.review(digest)
        blocked = prepare_setup(service, request.model_copy(update={'structure': 'direct'}))
        assert blocked['status'] == 'blocked' and blocked['reasons']
        result = prepare_setup(service, request)
        assert result['budget']['evaluation_stage'] == 'qualification'
        assert result['budget']['minimum_trial_model_turns'] == 141
        assert result['structure_choices']['selected'] == 'workflow'
        assert not result['execution_authorized']
        skill_config = dict(routes[1].config['invocation'])
        routes[1].config['invocation'] = dict(routes[0].config['invocation'])
        with pytest.raises(ConfigurationError, match='candidate invocation'):
            prepare_setup(service, request)
        routes[1].config['invocation'] = skill_config
        routes[1].config['invocation']['skill_sha256'] = 'e' * 64
        with pytest.raises(ConfigurationError, match='selected plugin'):
            prepare_setup(service, request)
        routes[1].config['managed_worker'] = None
        routes[1].config['argv'] = [sys.executable]
        with pytest.raises(ConfigurationError, match='legacy read-only'):
            prepare_setup(service, request)
        assert router.store._connection.execute('SELECT count(*) FROM assessment_operations').fetchone()[0] == 0
    finally:
        await router.close()


def test_real_boundary_gate_requires_catalog_image_and_offline_fixture_configuration(tmp_path, monkeypatch):
    from aeep.assessment import verification

    calls = []
    monkeypatch.setattr(verification, '_pytest', lambda root,args: (calls.append(args) or True, ''))
    for name in ('AEEP_CONTAINER_IMAGE','AEEP_WORKBOOK_IMAGE','AEEP_CONTAINER_RUNTIME','AEEP_CONTAINER_SOCKET'):
        monkeypatch.setenv(name,'fixture-only')
    for name in ('AEEP_CATALOG_METRICS_IMAGE','AEEP_INSPECTION_FIXTURE_SPECS'):
        monkeypatch.delenv(name,raising=False)
    missing = verification.verify_assessment_product(tmp_path,real_container=True)
    assert not missing.untrusted_plugin_containment and len(calls)==1
    assert 'catalog images' in missing.failure_detail
    monkeypatch.setenv('AEEP_CATALOG_METRICS_IMAGE','fixture-only')
    monkeypatch.setenv('AEEP_INSPECTION_FIXTURE_SPECS','fixture-only')
    available = verification.verify_assessment_product(tmp_path,real_container=True)
    assert available.untrusted_plugin_containment and not available.release_ready
    assert calls[-1][0:2]==['-m','real_container'] and 'tests/test_v08_managed_workers.py' in calls[-1]
