"""Prepare an expiry-only renewal and verify it on a private copy."""

from datetime import timedelta

from freeze_study import DATABASE
from prepare_runtime import DESIGN, DESIGN_SHA256, WORK, read, sha, write

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore


def snapshot():
    with ReceiptStore(DATABASE, read_only=True) as store:
        repo = AssessmentRepository(store)
        original = AssessmentAuthorization.model_validate(repo.get("authorization", "onboarding"))
        effective = repo.effective_grant("onboarding")
        counters = tuple(
            store._connection.execute(
                "SELECT revoked, operations, model_turns, elapsed_seconds, cash_usd "
                "FROM assessment_grants WHERE id='onboarding'"
            ).fetchone()
        )
        predecessor = store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='budget_amendment' "
            "AND json_extract(payload_json,'$.authorization_id')='onboarding' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0]
        reserved = [
            tuple(row)
            for row in store._connection.execute(
                "SELECT id FROM assessment_operations WHERE grant_id='onboarding' "
                "AND state='reserved' ORDER BY id"
            )
        ]
    assert counters[0] == 0 and float(counters[-1]) == 0
    return original, effective, counters, predecessor, reserved


def prepare():
    assert sha(DESIGN) == DESIGN_SHA256
    original, effective, counters, predecessor, reserved = snapshot()
    proposed = read(DESIGN)["grant_readback"]
    assert (
        not counters[0]
        and list(counters[1:]) == proposed["current_counters"]
        and effective.limits.model_dump(mode="json") == proposed["current_limits"]
        and predecessor == proposed["previous_budget_amendment"]
    )
    now = utc_now()
    amendment = AssessmentBudgetAmendment(
        authorization_id="onboarding",
        authorization_digest=content_digest(original),
        previous_amendment_digest=predecessor,
        limits=effective.limits,
        issued_at=now,
        expires_at=now + timedelta(days=7),
    )
    assert amendment.expires_at > effective.expires_at
    destination = WORK / "renewal-copy.sqlite3"
    assert not destination.exists()
    with ReceiptStore(DATABASE, read_only=True) as source, ReceiptStore(destination) as copied:
        source._connection.backup(copied._connection)
        repo = AssessmentRepository(copied)
        repo.approve_budget_amendment(amendment)
        new = repo.effective_grant("onboarding")
        assert new.limits == effective.limits and new.expires_at == amendment.expires_at
        assert (
            tuple(
                copied._connection.execute(
                    "SELECT revoked, operations, model_turns, elapsed_seconds, cash_usd "
                    "FROM assessment_grants WHERE id='onboarding'"
                ).fetchone()
            )
            == counters
        )
        assert [
            tuple(row)
            for row in copied._connection.execute(
                "SELECT id FROM assessment_operations WHERE grant_id='onboarding' "
                "AND state='reserved' ORDER BY id"
            )
        ] == reserved
    assert snapshot() == (original, effective, counters, predecessor, reserved)
    write(WORK / "expiry-only-renewal.json", amendment.model_dump(mode="json"))
    write(
        WORK / "expiry-only-renewal-audit.json",
        {
            "canonical_amendment_digest": content_digest(amendment),
            "file_sha256": sha(WORK / "expiry-only-renewal.json"),
            "prior_expiry": effective.expires_at.isoformat(),
            "proposed_expiry": amendment.expires_at.isoformat(),
            "unchanged_counters": counters[1:],
            "unchanged_limits": amendment.limits.model_dump(mode="json"),
            "previous_amendment": predecessor,
            "prior_reservation_count": len(reserved),
            "prior_reservations_sha256": content_digest(reserved),
            "copied_ledger_validated": True,
            "operational_ledger_amended": False,
        },
    )


if __name__ == "__main__":
    prepare()
