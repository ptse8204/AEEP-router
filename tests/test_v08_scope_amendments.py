from __future__ import annotations

import json

import pytest
from test_v08_assessment import setup_assessment

from aeep.assessment.models import (
    AssessmentBudgetAmendment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    content_digest,
)
from aeep.errors import ConfigurationError

pytestmark = pytest.mark.assessment_lifecycle


async def test_budget_expansion_preserves_history_and_rejects_stale_writers(tmp_path):
    from datetime import timedelta

    router, service, plan, grant = setup_assessment(tmp_path)
    repo = service.repository
    try:
        repo.reserve(plan, "spent", AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=5))
        repo.finish_operation("spent", elapsed_seconds=2)
        before = tuple(router.store._connection.execute("SELECT * FROM assessment_grants").fetchone())
        amendment = AssessmentBudgetAmendment(
            authorization_id=grant.authorization_id, authorization_digest=content_digest(grant),
            limits=grant.limits.model_copy(update={"max_model_turns": 6000}),
            expires_at=grant.expires_at + timedelta(days=1),
        )
        repo.approve_budget_amendment(amendment)
        repo.approve_budget_amendment(amendment)
        assert tuple(router.store._connection.execute("SELECT * FROM assessment_grants").fetchone()) == before
        assert repo.authorize(plan).limits.max_model_turns == 6000
        assert repo.get("authorization", grant.authorization_id) == grant.model_dump(mode="json")
        assert service.budget_preview(plan.plan_id)["remaining"]["model_turns"] == 6000
        stale = amendment.model_copy(update={"amendment_id": "stale"})
        with pytest.raises(ConfigurationError, match="predecessor"):
            repo.approve_budget_amendment(stale)
        changed = amendment.model_copy(update={"expires_at": grant.expires_at})
        with pytest.raises(ConfigurationError, match="immutable"):
            repo.approve_budget_amendment(changed)
        lower = amendment.model_copy(update={"amendment_id": "lower", "previous_amendment_digest": content_digest(amendment), "limits": grant.limits})
        with pytest.raises(ConfigurationError, match="ceilings"):
            repo.approve_budget_amendment(lower)
        assert len(repo.operation_ledger(plan.plan_id).operations) == 1
        repo.revoke(grant.authorization_id)
        with pytest.raises(ConfigurationError, match="unrevoked"):
            repo.approve_budget_amendment(stale)
    finally:
        await router.close()


async def test_budget_and_scope_bundle_roll_back_together(tmp_path):
    router, service, plan, grant = setup_assessment(tmp_path)
    repo = service.repository
    try:
        budget = AssessmentBudgetAmendment(authorization_id=grant.authorization_id,
            authorization_digest=content_digest(grant), limits=grant.limits.model_copy(update={"max_model_turns": 6000}),
            expires_at=grant.expires_at)
        scope = AssessmentScopeAmendment(authorization_id=grant.authorization_id,
            authorization_digest=content_digest(grant), subject_digests=[plan.subject_digest],
            recipe_digests=[plan.recipe_digest], environment_digests=[plan.environment_digest],
            reviewed_digests=plan.definition_digests)
        with pytest.raises(ConfigurationError, match="all scoped"):
            repo.approve_bundle(scope, {}, budget_amendment=budget)
        with pytest.raises(ConfigurationError, match="unknown"):
            repo.get("budget_amendment", budget.amendment_id)
        assert repo.effective_grant(grant.authorization_id).limits == grant.limits
    finally:
        await router.close()


async def test_budget_amendment_concurrency_expiry_and_successful_bundle(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta

    from aeep.models import utc_now

    router, service, plan, grant = setup_assessment(tmp_path)
    repo = service.repository
    try:
        proposal = AssessmentBudgetAmendment(authorization_id=grant.authorization_id,
            authorization_digest=content_digest(grant), limits=grant.limits, expires_at=grant.expires_at)
        def apply(identity):
            try:
                repo.approve_budget_amendment(proposal.model_copy(update={'amendment_id': identity}))
                return True
            except ConfigurationError:
                return False
        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(apply, ['writer-a', 'writer-b'])) == [False, True]
        latest = router.store._connection.execute("SELECT digest FROM assessment_records WHERE kind='budget_amendment'").fetchone()[0]
        future = proposal.model_copy(update={'amendment_id': 'future', 'previous_amendment_digest': latest, 'issued_at': utc_now()+timedelta(minutes=1)})
        with pytest.raises(ConfigurationError, match='ceilings'):
            repo.approve_budget_amendment(future)
        definitions = {digest: json.loads(payload) for digest, payload in router.store._connection.execute('SELECT digest,payload_json FROM assessment_records')}
        scope = AssessmentScopeAmendment(authorization_id=grant.authorization_id, authorization_digest=content_digest(grant),
            subject_digests=[plan.subject_digest], recipe_digests=[plan.recipe_digest], environment_digests=[plan.environment_digest], reviewed_digests=plan.definition_digests)
        amendment = proposal.model_copy(update={'amendment_id': 'bundle', 'previous_amendment_digest': latest})
        repo.approve_bundle(scope, definitions, budget_amendment=amendment)
        assert repo.effective_grant(grant.authorization_id).limits == grant.limits
        with pytest.raises(ConfigurationError, match='root authorization'):
            repo.approve_bundle(scope, definitions, budget_amendment=amendment.model_copy(update={'authorization_id': 'other'}))
        expired = grant.model_copy(update={'authorization_id': 'expired', 'issued_at': utc_now()-timedelta(days=2), 'expires_at': utc_now()-timedelta(days=1)})
        repo.grant(expired)
        renewal = proposal.model_copy(update={'amendment_id': 'renewal', 'authorization_id': expired.authorization_id,
            'authorization_digest': content_digest(expired)})
        repo.approve_budget_amendment(renewal)
        assert repo.effective_grant('expired').expires_at == grant.expires_at
    finally:
        await router.close()


async def test_scope_amendment_shares_existing_counters_and_is_atomic(tmp_path):
    router, service, plan, grant = setup_assessment(tmp_path)
    repository = service.repository
    try:
        repository.reserve(plan, "already-spent", AssessmentLimits(max_operations=1, max_elapsed_seconds=5))
        repository.finish_operation("already-spent", elapsed_seconds=2)
        definitions = {digest: json.loads(payload) for digest, payload in router.store._connection.execute(
            "SELECT digest, payload_json FROM assessment_records")}
        amendment = AssessmentScopeAmendment(authorization_id=grant.authorization_id,
            authorization_digest=content_digest(grant), subject_digests=[plan.subject_digest],
            recipe_digests=[plan.recipe_digest], environment_digests=[plan.environment_digest],
            reviewed_digests=plan.definition_digests)
        before = tuple(router.store._connection.execute("SELECT * FROM assessment_grants").fetchone())
        repository.approve_bundle(amendment, definitions)
        assert tuple(router.store._connection.execute("SELECT * FROM assessment_grants").fetchone()) == before
        assert repository.authorize(plan).limits == grant.limits
        repository.approve_bundle(amendment, definitions)  # Idempotent review cannot credit budget.
        assert tuple(router.store._connection.execute("SELECT * FROM assessment_grants").fetchone()) == before
        assert len(repository.operation_ledger(plan.plan_id).operations) == 1
        changed = amendment.model_copy(update={"reviewed_digests": [plan.recipe_digest]})
        with pytest.raises(ConfigurationError, match="immutable"):
            repository.approve_bundle(changed, definitions)
        repository.review(plan.recipe_digest, revoke=True)
        bad = dict(definitions)
        bad[plan.recipe_digest] = {"tampered": True}
        with pytest.raises(ConfigurationError, match="changed"):
            repository.approve_bundle(amendment, bad)
        with pytest.raises(ConfigurationError, match="review"):
            repository.authorize(plan)
        with pytest.raises(ConfigurationError, match="all scoped"):
            repository.approve_bundle(amendment, {})
        repository.revoke(grant.authorization_id)
        with pytest.raises(ConfigurationError, match="unrevoked"):
            repository.approve_bundle(amendment, definitions)
    finally:
        await router.close()


async def test_grant_record_and_counters_commit_together(tmp_path):
    import sqlite3

    router, service, _plan, grant = setup_assessment(tmp_path)
    new_grant = grant.model_copy(update={'authorization_id':'failed-transaction'})
    try:
        with router.store._connection:
            router.store._connection.execute("CREATE TEMP TRIGGER fail_grant BEFORE INSERT ON assessment_grants WHEN NEW.id='failed-transaction' BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with pytest.raises(sqlite3.IntegrityError, match='injected'):
            service.repository.grant(new_grant)
        with pytest.raises(ConfigurationError, match='unknown'):
            service.repository.get('authorization',new_grant.authorization_id)
        assert router.store._connection.execute("SELECT count(*) FROM assessment_grants WHERE id=?",(new_grant.authorization_id,)).fetchone()[0] == 0
    finally:
        await router.close()
