"""Receipt-derived operator text, without model/task dispatch or payload disclosure."""
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from aeep.cli import app
from aeep.models import TaskExecutionOutcome
from aeep.task_cli import control_commands, result_text

pytestmark = pytest.mark.assessment_lifecycle


def outcome():
    return TaskExecutionOutcome.model_validate({
        'ok': True, 'status': 'success', 'output': {'private': 'DO-NOT-DISPLAY'},
        'decision': {'decision_id': 'dec_x', 'action_id': 'a', 'capability': 'workbook',
                     'selected': 'native.workbook', 'reason': 'lowest feasible burden'},
        'summary': 'Completed; recorded non-schema task checks passed.',
        'approval_ceiling': 'read', 'verification_limits': ['Preservation is not established.'],
        'recovery_state': 'none'})


def test_text_is_receipt_derived_and_omits_output():
    value = outcome()
    text = result_text(value)
    assert 'native.workbook (lowest feasible burden)' in text
    assert 'Changes verified: unknown' in text
    assert 'Preservation is not established' in text
    assert 'missing measurements are unknown, not zero' in text
    assert 'Pause/undo commands unavailable' in text
    assert 'DO-NOT-DISPLAY' not in text
    assert value.output == {'private': 'DO-NOT-DISPLAY'}


def test_recovery_text_does_not_authorize_retry():
    value = outcome().model_copy(update={'ok': False, 'recovery_state': 'required'})
    assert 'reconcile the recorded attempt before retrying' in result_text(value)


def test_control_commands_bind_activation_and_quote_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / 'project with spaces.json'
    manifest.write_text('{}')
    router = SimpleNamespace(manifest_path=manifest)
    monkeypatch.setattr('aeep.task_cli.inspect', lambda *args: {'activation_id': 'task_owned', 'scope_digest': 'scope'})
    commands = control_commands(router, 'task_owned', 'scope')
    assert commands is not None and "'" + str(manifest) + "'" in commands[0]
    assert 'control pause task_owned' in commands[1]
    assert 'control rollback task_owned' in commands[2]
    assert 'does not match' in control_commands(router, 'task_owned', 'different')[0]
    manifest.unlink()
    assert control_commands(router, 'task_owned', 'scope') is None


def test_non_task_text_fails_before_router_or_tool_call(monkeypatch):
    monkeypatch.setattr('aeep.cli.Router.from_manifest', lambda *args: pytest.fail('must not open router'))
    result = CliRunner().invoke(app, ['tool-call', 'aeep_csv', '--text'])
    assert result.exit_code != 0 and 'only for the task profile' in result.output


@pytest.fixture
def retained_task(tmp_path):
    import asyncio
    from datetime import timedelta

    from aeep.assessment.models import content_digest
    from aeep.assessment.onboarding import reference_spec
    from aeep.assessment.repository import AssessmentRepository
    from aeep.economic.prepared import executor_fingerprint
    from aeep.models import ActionRequest, ExecutionReceipt, Manifest, TaskScope, utc_now
    from aeep.router import Router
    from aeep.tasks import TaskActivation

    spec = reference_spec('csv')
    manifest = tmp_path / 'aeep.json'
    manifest.write_text(Manifest(database=str(tmp_path / 'state.db'), executors=[spec]).model_dump_json())
    router = Router.from_manifest(manifest)
    repo = AssessmentRepository(router.store)
    scope = TaskScope(scope_id='presentation', project_root=str(tmp_path.resolve()),
        executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=2,
        max_attempt_seconds=10, expires_at=utc_now() + timedelta(minutes=5))
    digest = repo.put('task_scope', scope.scope_id, scope)
    repo.review(digest)
    decision = router.route(ActionRequest(capability=spec.capability, input={'text': 'a\n1', 'delimiter': ','}))
    router.store.save_decision(decision)
    receipt = ExecutionReceipt(decision_id=decision.decision_id, action_id=decision.action.action_id,
        capability=spec.capability, executor_id=spec.id, executor_kind=spec.kind, status='success',
        estimated=decision.candidates[0].estimate, executor_fingerprint=executor_fingerprint(spec),
        metadata={'task_scope_digest': digest})
    router.store.save_receipt(receipt)
    activation = TaskActivation(scope_digest=digest, manifest_digest=content_digest(router.manifest),
        manifest_path=str(manifest.resolve()))
    repo.put('task_activation', activation.activation_id, activation)
    repo.review(content_digest(activation), revoke=True)
    overlay = tmp_path / '.aeep/task-profiles' / (activation.activation_id + '.json')
    overlay.parent.mkdir(parents=True)
    overlay.write_text('user-edited conflict')
    asyncio.run(router.close())
    return manifest, receipt.receipt_id, activation.activation_id, overlay


def test_actual_store_receipt_json_and_paused_conflict_text(retained_task):
    import json
    manifest, receipt, activation, overlay = retained_task
    runner = CliRunner()
    args = ['task', '-m', str(manifest), 'result', receipt]
    ordinary = runner.invoke(app, args)
    assert ordinary.exit_code == 0, ordinary.output
    value = json.loads(ordinary.stdout)
    assert value['receipts'][0]['receipt_id'] == receipt
    assert value['output'] is None and value['changes_verified'] is None
    text = runner.invoke(app, [*args, '--text', '--activation', activation])
    assert text.exit_code == 0, text.output
    assert 'control pause ' + activation in text.stdout
    assert 'control rollback ' + activation in text.stdout
    assert 'historical runtime approval are not retained' in text.stdout
    assert 'at most 2 attempts' in text.stdout
    assert overlay.read_text() == 'user-edited conflict'
    missing = runner.invoke(app, [*args, '--text', '--activation', 'task_missing'])
    assert missing.exit_code == 0 and 'could not be inspected' in missing.stdout
    assert 'Completed;' in missing.stdout
    inspected = runner.invoke(app, ['task', '-m', str(manifest), 'control', 'inspect', activation, '--text'])
    assert inspected.exit_code == 0 and 'Reviewed: False' in inspected.stdout and 'overlay=conflict' in inspected.stdout


def test_tool_rejection_text_keeps_type_and_ceiling_without_payload(retained_task, monkeypatch):
    import json

    from aeep.mcp.server import AEEPToolService
    manifest, _, _, _ = retained_task

    async def reject(*args):
        return {'isError': True, 'structuredContent': {'error': 'DO-NOT-DISPLAY secret payload',
                'error_type': 'ApprovalRequired', 'required_level': 'write', 'code': 403}}

    monkeypatch.setattr(AEEPToolService, 'call', reject)
    args = ['tool-call', 'aeep_csv', '-m', str(manifest), '--profile', 'task']
    text = CliRunner().invoke(app, [*args, '--text'])
    assert text.exit_code == 4, text.output
    error = json.loads(text.stdout)
    assert error['code'] == 403 and error['error_type'] == 'ApprovalRequired'
    assert error['required_level'] == 'write' and 'DO-NOT-DISPLAY' not in text.stdout
    ordinary = CliRunner().invoke(app, args)
    assert ordinary.exit_code == 4 and json.loads(ordinary.stdout)['error'] == 'DO-NOT-DISPLAY secret payload'
