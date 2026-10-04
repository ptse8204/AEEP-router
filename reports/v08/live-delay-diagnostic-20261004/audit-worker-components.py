"""Read canonical metadata and Docker state; write exclusive terminal audit files."""
import hashlib
import json
import math
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
DB = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
DOCKER = ["/usr/local/bin/docker", "--host", "unix:///Users/edwintse/.docker/run/docker.sock"]
RESULT = OUT / "c-worker-components-result-v2.json"
PROXY = OUT / "c-worker-components-v3-proxy-result.json"
PREP = OUT / "c-worker-components-preparation-v2.json"
REVIEW = OUT / "c-worker-components-execution-review-v2.json"
PROXY_REVIEW = OUT / "c-worker-components-v3-proxy-review.json"
AUDIT = OUT / "c-worker-components-terminal-audit.json"
COST_AUDIT = OUT / "c-worker-components-parent-cost-audit.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    if AUDIT.exists() or COST_AUDIT.exists():
        raise ValueError("preserve the existing audit; do not replace it")
    assert verification_source_digest(ROOT) == SOURCE
    result, proxy, prep = [json.loads(path.read_text()) for path in (RESULT, PROXY, PREP)]
    assert all(value["source_digest"] == SOURCE for value in (result, proxy, prep))
    assert result["review_sha256"] == sha(REVIEW) and proxy["review_sha256"] == sha(PROXY_REVIEW)
    assert result["source_unchanged"] is True and proxy["source_unchanged"] is True
    assert result["component_probes_match"] is True and result["model_turns"] == proxy["model_turns"] == 0
    assert result["component_evidence_only"] is True and result["full_conformance"] is False
    assert result["qualification"] is False and result["request_ids"] == prep["request_ids"]
    assert proxy["status"] == "passed" and proxy["inner_result_sha256"] == sha(RESULT)
    assert proxy["proxy_restored_stopped"] is True and proxy["cleanup_operation_settled"] is True
    assert proxy["allowances_satisfied"] is True and proxy["coordinator_closed"] is True
    operations, probes, counts = [], [], {}
    connection = sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")

    def record(kind, identity):
        rows = connection.execute("SELECT digest,payload_json FROM assessment_records WHERE kind=? AND (id=? OR digest=?)",
                                  (kind, identity, identity)).fetchall()
        assert len(rows) == 1
        digest, payload = rows[0]
        value = json.loads(payload)
        assert content_digest(value) == digest
        return digest, value

    def operation(identity, plan_id):
        row = connection.execute("SELECT grant_id,state,reserved_json FROM assessment_operations WHERE id=?", (identity,)).fetchone()
        assert row is not None and row[:2] == ("onboarding", "complete")
        start_digest, start = record("operation_start", identity)
        measurement_digest, measured = record("operation_measurement", identity)
        assert start["operation_id"] == measured["operation_id"] == identity
        assert start["plan_id"] == measured["plan_id"] == plan_id
        assert start["reserved"] == measured["reserved"] == json.loads(row[2])
        assert measured["reserved"]["max_model_turns"] == 0
        elapsed = measured["elapsed_seconds"]
        assert isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and 0 <= elapsed <= measured["reserved"]["max_elapsed_seconds"]
        operations.append({"id": identity, "state": row[1], "grant_id": row[0], "elapsed_seconds": elapsed})
        return start_digest, measurement_digest, elapsed

    try:
        for role, request_id in zip(("control", "treatment"), prep["request_ids"], strict=True):
            worker = result["workers"][role]
            _, request = record("conformance_request", request_id)
            assert request == next(value for value in prep["requests"] if value["plan_id"] == request_id)
            assert request["authorization_id"] == "onboarding" and request["worker_digest"] == worker["worker_digest"]
            parent_digest, measurement_digest, _ = operation("pair-inspection:" + request_id, request_id)
            _, inspection = record("worker_pair_inspection", "pair-inspection:" + request_id)
            observations = inspection["observations"]
            assert inspection["worker_digest"] == worker["worker_digest"]
            assert observations["cleanup_confirmed"] is True and observations["component_probes_match"] is True
            assert observations["model_turns"] == worker["model_turns"] == 0
            assert worker["cleanup_confirmed"] is True and worker["luna_present_once"] is True and worker["xhigh_available"] is True
            assert inspection["execution_evidence_digest"] == worker["execution_evidence_digest"]
            _, evidence = record("execution_evidence", worker["execution_evidence_digest"])
            assert evidence["complete"] is True and evidence["events"][-1]["kind"] == "execution.completed"
            names = set()
            for digest in worker["probe_digests"]:
                actual_digest, probe = record("boundary_probe", digest)
                assert actual_digest == digest and probe["schema_version"] == "assessment.boundary-probe.v2"
                assert probe["worker_digest"] == request["worker_digest"]
                assert probe["charged_operation_digest"] == parent_digest
                assert probe["execution_evidence_digest"] == worker["execution_evidence_digest"]
                assert probe["implementation_digest"] in request["definition_digests"]
                _, definition = record("boundary_probe_definition", probe["implementation_digest"])
                assert definition == prep["definitions"][probe["implementation_digest"]]
                assert probe["name"] == definition["name"] and probe["observed"] == definition["expected"]
                assert probe["name"] not in names
                names.add(probe["name"])
                probes.append({"role": role, "probe_digest": digest, "name": probe["name"],
                               "charged_operation_digest": parent_digest, "measurement_digest": measurement_digest})
            assert len(names) == 11 and {"cleanup", "credential_canary", "cross_worker", "candidate_access"} <= names
            counts[role] = len(names)
        assert len(probes) == 22
        expected_proxy_ids = {proxy["request_id"] + ":" + suffix for suffix in ("proxy_preflight", "proxy_start", "proxy_stop")}
        assert set(proxy["measured_operation_seconds"]) == expected_proxy_ids
        for identity, elapsed in proxy["measured_operation_seconds"].items():
            assert operation(identity, proxy["request_id"])[2] == elapsed
        grant = connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd,revoked FROM assessment_grants WHERE id='onboarding'").fetchone()
        assert grant is not None and grant[4] == 0
    finally:
        connection.close()
    running = subprocess.check_output(DOCKER + ["ps", "--format", "{{.ID}}"], text=True, timeout=15).splitlines()
    stopped = subprocess.check_output(DOCKER + ["inspect", "--format", "{{.State.Running}}", proxy["proxy_id"]], text=True, timeout=15).strip() == "false"
    assert stopped and not running
    assert verification_source_digest(ROOT) == SOURCE
    write(COST_AUDIT, {"source_digest": SOURCE, "status": "passed", "probe_count": 22,
                      "parent_operation_count": 2, "probes": probes, "model_turns": 0})
    files = (RESULT, PROXY, PREP, REVIEW, PROXY_REVIEW, OUT / "c-current-profile-v2.json", Path(__file__))
    audit = {"recorded_at": datetime.now(timezone.utc).isoformat(), "source_digest": SOURCE,
             "status": "both zero-turn worker component inspections passed", "probe_counts": counts,
             "operations": operations, "model_turns": 0, "actual_worker_cleanup_confirmed": True,
             "proxy_restored_stopped": True, "global_running_container_count": len(running),
             "global_container_inventory": "Docker ps observed no running containers at audit time",
             "canonical_parent_costs_verified": True, "parent_cost_audit_sha256": sha(COST_AUDIT),
             "files": {path.name: sha(path) for path in files},
             "grant_at_metadata_audit": dict(zip(("operations", "model_turns", "elapsed_seconds", "cash_usd", "revoked"), grant, strict=True)),
             "whole_system_cost_complete": False, "full_conformance": False, "qualification": False,
             "value_or_benefit": False, "past_failures_preserved": ["profile-v1-preparation-stop.json"]}
    write(AUDIT, audit)
    print(json.dumps({"audit": str(AUDIT), "sha256": sha(AUDIT), "helper_sha256": sha(Path(__file__)),
                      "probe_count": 22, "settled_operations": len(operations), "running_containers": len(running)}))


if __name__ == "__main__":
    main()
