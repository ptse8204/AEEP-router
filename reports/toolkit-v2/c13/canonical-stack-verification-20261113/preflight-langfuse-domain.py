"""Read-only audit of the retained service and exact paired-domain payloads."""

import hashlib
import importlib.util
import json
import socket
from pathlib import Path

from aeep.assessment.models import AssessmentPlan, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep.telemetry import receipt_otlp_preview
from aeep_toolkit.workflow_telemetry import campaign_receipt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
PRIOR = C13 / "langfuse-ingestion-readback-20261105"
spec = importlib.util.spec_from_file_location("retained_controls", PRIOR / "run.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
runtime, base = previous.runtime, previous.base


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle,"sha256").hexdigest()


def audit():
    retained = read(PRIOR / "operation-review.json")
    draft = read(HERE / "domain-telemetry-preflight.json")
    assert draft["implementation_source"] == verification_source_digest(ROOT)
    executable_drift = {
        path: {"reviewed": digest, "observed": current}
        for path, digest in retained["executables"].items()
        if (current := sha(Path(path).resolve())) != digest
    }
    IDs = [retained["containers"][name] for name in base.SERVICES]
    observed = runtime.safe_read(retained, "inspect", "--format", runtime.STATE_TEMPLATE, *IDs)
    for name, line in zip(base.SERVICES, observed.splitlines(), strict=True):
        ident, state, status, labels = tuple(runtime.decode(line))
        assert ident == retained["containers"][name] and state == "exited"
        assert labels[base.LABEL] == runtime.PROJECT and labels["com.docker.compose.service"] == name
        if name not in runtime.LIVE:
            assert status == 0
    permissions = runtime.check_permissions(retained, IDs)
    with socket.socket() as verify:
        verify.bind(("127.0.0.1", base.PORT))
    prior_counters, prior_receipt_ref, _ = previous.latest(retained)
    preflight = {
        "retained_namespace":runtime.PROJECT,"retained_containers":len(IDs),"running_containers":0,
        "permission_audit":permissions,"loopback_port_available":base.PORT,
        "executable_drift":executable_drift,
        "service_grant_authorization_id":retained["grant_authorization_id"],"counters":prior_counters,
        "existing_transport_receipt":prior_receipt_ref,"new_service_starts":0,"new_models":0,
        "caps": {"operations":retained["maximum_operations"], "reserved_seconds":retained["maximum_reserved_seconds"]},
    }
    with ReceiptStore(draft["database"],read_only=True) as store:
        repo = AssessmentRepository(store)
        bindings = {}
        for domain, configuration in draft["configurations"].items():
            variant, = [row for row in configuration["variants"] if row["enabled"]]
            assert all(sha(variant[key]["path"]) == variant[key]["sha256"]
                       for key in ("workflow","accounting","definition"))
            workflow = read(variant["workflow"]["path"])
            selected = workflow["configurations"][domain]
            plan = AssessmentPlan.model_validate(read(selected["assessment"]["plan"]["path"]))
            request = RecipeMaterializationRequest.model_validate(read(variant["definition"]["path"])["request"])
            receipt = campaign_receipt(repo,configuration["report_ref"],configuration["receipt_id"],plan,request)
            preview=receipt_otlp_preview(receipt)
            span=preview["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
            for attribute in span["attributes"]:
                if attribute["key"]=="aeep.evidence.trust":
                    attribute["value"]={"stringValue":"canonical_store_receipt"}
            assert content_digest(preview["payload"]) == configuration["minimized_payload_sha256"]
            assert preview["receipt_sha256"]==configuration["source_receipt_sha256"]
            bindings[domain]={"receipt":preview["receipt_sha256"],"trace":span["traceId"],"span":span["spanId"]}
    return preflight|{"trace_bindings":bindings,"execution":"UNSTARTED","comparisons":"PAUSED"}


if __name__=="__main__":
    print(json.dumps(audit(),indent=2))
