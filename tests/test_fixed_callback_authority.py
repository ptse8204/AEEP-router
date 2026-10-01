from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from test_fixed_helper import fixed as fixed
from test_v08_assessment import setup_assessment

from aeep.assessment.fixed_helper import AssessmentCallbackAuthority
from aeep.assessment.models import AssessmentLimits, content_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.errors import ConfigurationError
from aeep.hosts.codex_dynamic_tools import DynamicCallContext, _call_context
from aeep.hosts.codex_invocation import contract_digest
from aeep.models import SideEffect


async def test_callback_claim_replay_and_outer_authority(tmp_path, fixed):
    router, assessment, plan, _grant = setup_assessment(tmp_path)
    repo = assessment.repository
    job = assessment.enqueue(plan.plan_id)
    with router.store._immediate_transaction() as connection:
        connection.execute("UPDATE assessment_jobs SET state='running' WHERE id=?", (job,))
    repo.reserve(plan, "trial", AssessmentLimits(max_operations=1, max_elapsed_seconds=20), stage="trial")
    router._callback_trial_identity = (job, "trial")
    router._trial_check = lambda: repo.authorize(plan)
    outer_attempt = router.store.create_execution_attempt(ExecutionAttempt(attempt_id="outer", decision_id="outer-decision", action_digest="a"*64, executor_id=plan.candidate_id, executor_fingerprint="b"*64, side_effect=SideEffect.READ, idempotent=True, owner_id="owner", state="INVOKING", invocation_start_digest="sha256:"+"c"*64))
    authority = AssessmentCallbackAuthority(assessment, plan, job, "trial", outer_router=router,
        outer_attempt_id=outer_attempt.attempt_id, binding_digest="a"*64, resolve_binding=lambda: "a"*64, max_calls=1)
    calls = []
    async def call(name, args):
        calls.append(name)
        return {"isError": False}
    child_router, _repo, _scope, _digest, _spec = fixed
    service = SimpleNamespace(router=child_router, call=call)
    links = []
    context = DynamicCallContext(contract_digest({"attempt_id": outer_attempt.attempt_id}), "c"*64, "dynamic_"+"c"*64, links.append)
    token = _call_context.set(context)
    try:
        results = await asyncio.gather(*(authority.call(service, "fixed", {}) for _ in range(2)), return_exceptions=True)
        assert len(calls) == 1 and len(links) == 1
        assert sum(isinstance(value, ConfigurationError) for value in results) == 1
        claim_key = content_digest({"outer_operation": hashlib.sha256(b'trial').hexdigest(), "call": "c"*64})
        assert repo.get("callback_evidence", claim_key)["resources_overlap_outer_trial"]
        assert repo.operation_ledger(plan.plan_id).operations[0].elapsed_seconds is None
        router._callback_trial_identity = (job, "another-trial")
        with pytest.raises(ConfigurationError, match="identity"):
            authority.check()
        router._callback_trial_identity = (job, "trial")
        repo.finish_operation("trial", elapsed_seconds=0)
        with pytest.raises(ConfigurationError, match="reserved"):
            authority.check()
    finally:
        _call_context.reset(token)
        await child_router.close()
        await router.close()


@pytest.mark.parametrize("invalid", ["expired", "future", "monotonic", "revoked", "attempt_terminal", "bool", "fraction"])
async def test_callback_rejects_stale_authority(tmp_path, invalid, monkeypatch):
    router, assessment, plan, _grant = setup_assessment(tmp_path)
    repo = assessment.repository
    job = assessment.enqueue(plan.plan_id)
    with router.store._immediate_transaction() as connection:
        connection.execute("UPDATE assessment_jobs SET state='running' WHERE id=?", (job,))
    repo.reserve(plan, "trial", AssessmentLimits(max_operations=1, max_elapsed_seconds=20), stage="trial")
    router._callback_trial_identity = (job, "trial")
    router._trial_check = lambda: repo.authorize(plan)
    outer_attempt = router.store.create_execution_attempt(ExecutionAttempt(attempt_id="outer", decision_id="outer-decision", action_digest="a"*64, executor_id=plan.candidate_id, executor_fingerprint="b"*64, side_effect=SideEffect.READ, idempotent=True, owner_id="owner", state="INVOKING", invocation_start_digest="sha256:"+"c"*64))
    authority = AssessmentCallbackAuthority(assessment, plan, job, "trial", outer_router=router,
        outer_attempt_id=outer_attempt.attempt_id, binding_digest="a"*64, resolve_binding=lambda: "a"*64, max_calls=1)
    try:
        if invalid in {"bool", "fraction"}:
            with pytest.raises(ConfigurationError, match="binding"):
                AssessmentCallbackAuthority(assessment, plan, job, "trial", outer_router=router,
                    outer_attempt_id=outer_attempt.attempt_id, binding_digest="a"*64,
                    resolve_binding=lambda: "a"*64, max_calls=True if invalid == "bool" else 1.5)
            return
        if invalid in {"expired", "future"}:
            from datetime import timedelta

            from aeep.models import utc_now
            monkeypatch.setattr("aeep.models.utc_now", lambda: utc_now()+timedelta(minutes=5 if invalid == "expired" else -5))
        elif invalid == "monotonic":
            router._trial_deadline = asyncio.get_running_loop().time()-1
        elif invalid == "revoked":
            repo.review(plan.mapping_digest, revoke=True)
        else:
            with router.store._immediate_transaction() as connection:
                # Exact existing canonical state transition, not a descriptor-only check.
                connection.execute("UPDATE execution_attempts SET payload_json=? WHERE attempt_id=?",
                    (outer_attempt.model_copy(update={"state": ExecutionAttemptState.FAILED}).model_dump_json(), outer_attempt.attempt_id))
        with pytest.raises(ConfigurationError):
            authority.check()
    finally:
        await router.close()


async def test_callback_cancellation_retains_child_attempt_link(tmp_path, monkeypatch, fixed):
    router, assessment, plan, _grant = setup_assessment(tmp_path)
    repo = assessment.repository
    job = assessment.enqueue(plan.plan_id)
    with router.store._immediate_transaction() as connection:
        connection.execute("UPDATE assessment_jobs SET state='running' WHERE id=?", (job,))
    repo.reserve(plan, "trial", AssessmentLimits(max_operations=1, max_elapsed_seconds=20), stage="trial")
    router._callback_trial_identity = (job, "trial")
    router._trial_check = lambda: repo.authorize(plan)
    outer_attempt = router.store.create_execution_attempt(ExecutionAttempt(attempt_id="outer", decision_id="outer-decision", action_digest="a"*64, executor_id=plan.candidate_id, executor_fingerprint="b"*64, side_effect=SideEffect.READ, idempotent=True, owner_id="owner", state="INVOKING", invocation_start_digest="sha256:"+"c"*64))
    authority = AssessmentCallbackAuthority(assessment, plan, job, "trial", outer_router=router,
        outer_attempt_id=outer_attempt.attempt_id, binding_digest="a"*64, resolve_binding=lambda: "a"*64, max_calls=1)
    child_router, _repo, _scope, _digest, spec = fixed
    from aeep.executors.command import CommandExecutor
    from aeep.models import ActionRequest
    started = asyncio.Event()
    async def pending(self, execution_context):
        started.set()
        await asyncio.Future()
    monkeypatch.setattr(CommandExecutor, "execute", pending)
    async def call(name, arguments):
        request = ActionRequest(action_id="dynamic_"+"c"*64, capability=spec.capability,
                                input={"text": "", "delimiter": ","})
        await child_router.execute_fixed(request, spec.id)
        raise AssertionError("cancelled invocation returned")
    links = []
    context = DynamicCallContext(contract_digest({"attempt_id": outer_attempt.attempt_id}), "c"*64,
                                 "dynamic_"+"c"*64, links.append)
    token = _call_context.set(context)
    try:
        task = asyncio.create_task(authority.call(SimpleNamespace(router=child_router, call=call), "fixed", {}))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(links) == 1
        evidence = repo.get("callback_evidence", content_digest({"outer_operation": hashlib.sha256(b"trial").hexdigest(), "call": "c"*64}))
        assert evidence["child_attempt_digests"]
        assert not child_router._fixed_dispatches
    finally:
        _call_context.reset(token)
        await child_router.close()
        await router.close()
