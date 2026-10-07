from __future__ import annotations

import sys
from datetime import timedelta

import pytest

from aeep.assessment.models import content_digest
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.attempts import ExecutionAttemptState
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import (
    ActionConstraints,
    ActionRequest,
    ExecutorKind,
    Manifest,
    PolicyConfig,
    SideEffect,
    TaskScope,
    utc_now,
)
from aeep.router import Router


@pytest.mark.parametrize("failure", ["exit", "timeout"])
@pytest.mark.skipif(sys.platform == "win32", reason="native task integration requires POSIX; Windows uses WSL")
async def test_fixed_partial_write_requires_recovery_after_restart(tmp_path, monkeypatch, failure):
    root = tmp_path.resolve()
    data = root / 'data'
    data.mkdir()
    effect = data / 'effect'
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    boundary = NativeSandboxConfig(binary=str(root / 'fixture'), binary_sha256='sha256:' + 'a'*64,
        project_root=str(root), write_roots=[str(data)])
    program = ('import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); '
               'p.write_text(p.read_text()+"effect\\n" if p.exists() else "effect\\n"); '
               + ('sys.exit(3)' if failure == 'exit' else 'time.sleep(10)'))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND,
        'side_effect': SideEffect.WRITE, 'idempotent': False, 'config': {
        'argv': [sys.executable, '-I', '-c', program, str(effect)], 'argv_literal': True,
        'native_sandbox': boundary.model_dump(mode='json'), 'timeout_seconds': 0.5}})
    manifest = Manifest(database=str(root / '.aeep' / 'state.db'), executors=[spec],
        policies={'write': PolicyConfig(name='write', constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))})
    request = ActionRequest(capability=spec.capability, policy='write', input={'text': 'a\n1', 'delimiter': ','},
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))
    router = Router(manifest, manifest_path=root / 'aeep.yaml')
    repo = AssessmentRepository(router.store)
    scope = TaskScope(scope_id='recovery', project_root=str(root),
        executor_fingerprints={spec.id: executor_fingerprint(spec)}, approval_ceiling=SideEffect.WRITE,
        max_attempts=3, max_attempt_seconds=1, expires_at=utc_now() + timedelta(minutes=5))
    digest = repo.put('task_scope', scope.scope_id, scope)
    repo.review(digest)
    router.bind_task_scope(scope.scope_id)
    try:
        outcome = await router.execute_fixed(request, spec.id, approved_side_effect=SideEffect.WRITE)
        assert not outcome.ok and effect.read_text() == 'effect\n'
        attempt = router.store.execution_attempt_for_decision(outcome.decision.decision_id)
        assert attempt is not None and attempt.state is ExecutionAttemptState.INDETERMINATE
        payload = router.task_outcome(outcome, approved_side_effect=SideEffect.WRITE)
        assert payload.recovery_state == 'required' and 'Reconcile' in payload.summary
    finally:
        await router.close()
    restarted = Router(manifest, manifest_path=root / 'aeep.yaml')
    try:
        repo = AssessmentRepository(restarted.store)
        repo.review(digest, revoke=True)
        repo.review(digest)
        restarted.bind_task_scope(scope.scope_id)
        with pytest.raises(ConfigurationError, match='recovery'):
            await restarted.execute_fixed(request, spec.id, approved_side_effect=SideEffect.WRITE)
        assert effect.read_text() == 'effect\n'  # Restart/pause/resume must not duplicate the write.
        assert restarted.store.get_receipt(outcome.receipts[0].receipt_id) is not None
        from aeep.tasks import TaskReconciliation, reconcile
        # Explicit operator inspection/reversal, never an automatic retry.
        effect.unlink()
        recovery = TaskReconciliation(attempt_id=attempt.attempt_id, attempt_version=attempt.version,
            scope_digest=digest, resolution='effects_reverted', evidence_digests=[digest])
        recovery_digest=repo.put('task_reconciliation',content_digest(recovery),recovery)
        with pytest.raises(ConfigurationError,match='review'):
            reconcile(restarted,recovery_digest)
        repo.review(recovery_digest)
        resolved=reconcile(restarted,recovery_digest)
        assert resolved['state']=='FAILED' and resolved['allowance_reset'] is False
        assert restarted.store.get_receipt(outcome.receipts[0].receipt_id) is not None
        with pytest.raises(ConfigurationError,match='exact unresolved'):
            reconcile(restarted,recovery_digest)
        retried = await restarted.execute_fixed(request, spec.id, approved_side_effect=SideEffect.WRITE)
        assert not retried.ok and effect.read_text() == 'effect\n'
        next_attempt = restarted.store.execution_attempt_for_decision(retried.decision.decision_id)
        assert next_attempt is not None and next_attempt.attempt_id != attempt.attempt_id
        assert next_attempt.state is ExecutionAttemptState.INDETERMINATE
        assert restarted.store._connection.execute('SELECT COUNT(*) FROM execution_attempts').fetchone()[0] == 2
    finally:
        await restarted.close()
