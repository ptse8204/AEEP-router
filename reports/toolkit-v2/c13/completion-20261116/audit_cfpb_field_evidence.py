"""Reopen the completed CFPB evidence without executing a recipe or model."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RECORD = HERE / "cfpb-cli-execution-result-20261117.json"
BASE = ROOT / ".aeep/completion-20261116"
WORK = BASE / "cfpb-managed-engineering-20261117/execution"


def read(path: Path):
    return json.loads(path.read_bytes())


def pin(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def audit():
    record = read(RECORD)
    dispatch = read(WORK / "dispatch-ready.json")
    campaign = WORK / "campaigns" / record["plan_id"]
    assert dispatch["plan_id"] == record["plan_id"]
    assert dispatch["plan_digest"] == record["plan_digest"]
    with closing(sqlite3.connect((campaign / "campaign.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        (trial_raw,) = db.execute("SELECT payload_json FROM trials").fetchone()
        trial = json.loads(trial_raw)
        (receipt_raw,) = db.execute("SELECT payload_json FROM trial_receipts WHERE trial_id=?", (trial["trial_id"],)).fetchone()
        (attempt,) = db.execute("SELECT database_path FROM trial_stores WHERE trial_id=?", (trial["trial_id"],)).fetchone()
    receipt = ExecutionReceipt.model_validate_json(receipt_raw)
    assert receipt.receipt_id == record["receipt_id"] and content_digest(receipt) == record["receipt_ref"]
    assert receipt.receipt_id in trial["receipt_ids"] and trial["case_id"] == record["case_id"]
    (grade,) = trial["case_validation"]
    assert grade == record["protected_check"] and grade["valid"] is False
    assert grade["quality_score"] == record["native_value_f1"] and not grade["detail"]
    assert record["worker_cleanup_confirmed"] and receipt.metadata["worker_cleanup_confirmed"]
    assert record["no_new_unresolved_operations"] is True

    attempts = sorted((campaign / "attempts").glob("*.sqlite3"))
    graders = sorted((campaign / "recipe-operations").glob("*.sqlite3"))
    assert Path(attempt) in attempts and graders
    stores = []
    for path in [*attempts, *graders]:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            (retained_artifacts,) = db.execute("SELECT COUNT(*) FROM content_artifacts").fetchone()
            replies = [json.loads(r[0]) for r in db.execute("SELECT payload_json FROM receipts")]
        assert retained_artifacts == 0
        assert all(reply.get("output") is None and reply["metadata"].get("prediction_b64") is None for reply in replies)
        if path == Path(attempt):
            (attempt_receipt,) = [item for item in replies if item["receipt_id"] == receipt.receipt_id]
            assert content_digest(ExecutionReceipt.model_validate(attempt_receipt)) == record["receipt_ref"]
        stores.append({"path": str(path.relative_to(ROOT)), "receipt_count": len(replies),
                       "retained_content_artifacts": retained_artifacts})

    for folder in ("cfpb-result", "cfpb-report"):
        evidence = read(WORK / folder / "managed-evidence.json")
        assert evidence["plan_sha256"] == record["plan_digest"]
        assert evidence["canonical_trials"] == 1 and record["journal_ref"] in evidence["execution_journals"]
        (run,) = read(WORK / folder / "toolkit-evidence.json")["runs"]
        assert run["receipt_refs"] == [record["receipt_ref"]]
        assert "prediction_b64" not in evidence and "feedback" not in evidence
        assert not any(path.is_file() for path in (WORK / folder).glob("*feedback*"))
    assert not list(WORK.rglob("feedback.json")) and not list(WORK.rglob("output.json"))

    source = BASE / "extractbench-cfpb-workflow-bound/protected-context"
    observer = source / "extractbench_harbor_observer.py"
    guest = source / "extractbench_recipe_guest.py"
    manifest = read(source.parent / "protected-context-manifest.json")
    for p in (observer, guest):
        assert pin(p)["sha256"] == manifest[p.name]
    assert "withholding paths and cells" in observer.read_text()
    assert "TemporaryDirectory" in guest.read_text()
    assert '"quality_scores": [score]' in guest.read_text()
    return {
        "schema_version": "aeep.c13.cfpb-field-evidence-audit.v1",
        "status": "FIELD_IDENTITIES_UNAVAILABLE",
        "execution_result": pin(RECORD),
        "case_id": record["case_id"],
        "plan_id": record["plan_id"],
        "trial_id": trial["trial_id"],
        "receipt_ref": record["receipt_ref"],
        "artifact_sha256": receipt.metadata["artifact_sha256"],
        "artifact_bytes": receipt.metadata["artifact_bytes"],
        "protected_grade": grade,
        "grader_observer": pin(observer),
        "grader_reply_bridge": pin(guest),
        "stores_examined": stores,
        "managed_evidence_examined": [pin(WORK / k / "managed-evidence.json") for k in ("cfpb-result", "cfpb-report")],
        "attribution_limit": "The retained score proves an inexact extraction. The verifier's per-field marker and the submitted bytes were transient. A file digest and aggregate score do not identify the affected fields or their count.",
        "model_turns": 0,
        "grader_runs": 0,
        "existing_records_changed": False,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
