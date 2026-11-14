"""Exercise the retained service with one previously unexported receipt."""

import argparse
import base64
import json
import runpy
import socket
import sys
import time
from pathlib import Path

from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentLimits, RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PARENT = runpy.run_path(str(HERE / "run-domain-telemetry.py"))
read, sha, save = (PARENT[key] for key in ("read", "sha", "save"))
runtime, base = PARENT["runtime"], PARENT["base"]
TAG = "langfuse-queue-acknowledgement-20261113"
DOMAIN = "document-excel"
MAX_SERVICE = 36
MAX_MANAGED = 5
MAX_MANAGED_SECONDS = 200


def variants(definitions):
    target = definitions["configurations"][DOMAIN]
    enabled, = (entry for entry in target["variants"] if entry["enabled"])
    disabled, = (entry for entry in target["variants"] if not entry["enabled"])
    return target, enabled, disabled


def service_request():
    return RecipeMaterializationRequest.model_validate(
        read(runtime.PRIOR / "prepared.json")["request"]
    ).model_copy(update={"plan_id": TAG})


def exercise(cli, scope, poll, target, enabled, disabled, auth):
    facts = {"disablement": False, "acknowledgement": None, "ingestion": False}
    preview = cli(disabled, "disable-preview")
    off = cli(disabled, "disabled", preview["review_sha256"])
    if off.get("status") != "disabled" or scope.counts["export"]:
        raise RuntimeError("DisablementFailed")
    facts["disablement"] = True
    preview = cli(enabled, "enable-preview")
    if (preview.get("acknowledgement") != "langfuse-4.55.0-queue"
            or preview["payload_sha256"] != target["minimized_payload_sha256"]):
        raise RuntimeError("ExportPreviewMismatch")
    try:
        result = cli(enabled, "export", preview["review_sha256"], auth)
    except AssertionError:
        result = None
    # Read back the one dispatched POST even if acknowledgement was rejected.
    if scope.counts["export"] == 1:
        facts["ingestion"] = poll("/api/public/v2/observations", expected=target, auth=auth, attempts=8)
    if (result and result.get("transport_accepted") is True and result.get("ingestion_verified") is False
            and result["trace_id"] == target["trace_id"] and result["span_id"] == target["span_id"]
            and result["source_receipt_sha256"] == target["source_receipt_sha256"]):
        facts["acknowledgement"] = result["transport_receipt_ref"]
    facts["posts"] = scope.counts["export"]
    return facts


def validate(p, check_current=True):
    review = read(p)
    assert all(sha(path) == expected for path, expected in review["pins"].items())
    data, parent = (read(review[name]) for name in ("bindings", "service_review"))
    retained = parent["retained_runtime"]
    assert review["implementation_source"] == data["implementation_source"] == verification_source_digest(ROOT)
    assert not Path(review["output"]).exists()
    target, enabled, disabled = variants(data)
    assert review["scope"] == {key: target[key] for key in
                               ("task", "receipt_id", "source_receipt_sha256", "trace_id", "span_id",
                                "minimized_payload_sha256")}
    assert all(sha(item[role]["path"]) == item[role]["sha256"] for item in (enabled, disabled)
               for role in ("workflow", "definition", "accounting"))
    request = service_request()
    with ReceiptStore(data["database"], read_only=True) as managed, ReceiptStore(retained["ledger"], read_only=True) as service:
        assert not managed._connection.execute("SELECT 1 FROM assessment_operations WHERE id LIKE ?",
            ("receipt-export:%:" + target["source_receipt_sha256"],)).fetchone()
        repo, lifecycle = AssessmentRepository(managed), AssessmentRepository(service)
        assert PARENT["counters"](repo, "onboarding") == review["managed_before"]
        assert PARENT["counters"](lifecycle, request.authorization_id) == review["service_before"]
        assert lifecycle.authorize(request).limits.max_model_turns == lifecycle.authorize(request).limits.max_cash_usd == 0
        assert not service._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? "
            "AND state='reserved'", (request.authorization_id,)).fetchone()
        assert not managed._connection.execute("SELECT 1 FROM assessment_operations WHERE id LIKE ?",
            ("workflow:skillsbench-langfuse-ack-%",)).fetchone()
        grant = repo.current_grant("onboarding")
        assert grant.limits.max_cash_usd == 0
        assert grant.limits.max_operations >= review["managed_before"][0] + MAX_MANAGED
        assert grant.limits.max_elapsed_seconds >= review["managed_before"][2] + MAX_MANAGED_SECONDS
        with ReceiptStore(":memory:") as draft:
            # These same approval and receipt resolvers run before the production launch.
            managed._connection.backup(draft._connection)
            for variant in (enabled, disabled):
                scope = PARENT["bind"](AssessmentRepository(draft), data, variant)
                PARENT["resolved"](AssessmentRepository(draft), target, variant, scope.request)
        with ReceiptStore(":memory:") as draft:
            service._connection.backup(draft._connection)
            copy = AssessmentRepository(draft)
            copy.approve_budget_amendment(AssessmentBudgetAmendment.model_validate(review["service_amendment"]))
            assert copy.authorize(request).limits.max_operations >= review["service_before"][0] + MAX_SERVICE
    base.validate(retained)
    ids = [retained["containers"][name] for name in base.SERVICES]
    rows = runtime.safe_read(retained, "inspect", "--format", runtime.STATE_TEMPLATE, *ids)
    for name, line in zip(base.SERVICES, rows.splitlines(), strict=True):
        identity, state, status, labels = tuple(runtime.decode(line))
        assert identity == retained["containers"][name] and state == "exited"
        assert labels[base.LABEL] == runtime.PROJECT and labels["com.docker.compose.service"] == name
        if name not in runtime.LIVE:
            assert status == 0
    assert runtime.check_permissions(retained, ids)
    with socket.socket() as standby:
        standby.bind(("127.0.0.1", base.PORT))
    if check_current:
        check = read(Path(review["source_verification"]))
        assert check["passed"] and check["source"] == review["implementation_source"]
    return review, data, retained


def execute(p, identity):
    review, data, retained = validate(p)
    target, enabled, disabled = variants(data)
    output, profiles = Path(review["output"]), Path(review["profiles"])
    output.mkdir(mode=0o700)
    (output / "service-execution").mkdir(mode=0o700)
    save(output / "started.json", {"review_sha256": identity, "models": 0})
    base.HERE = output
    request = service_request()
    result = {"passed": False, "review_sha256": identity, "scope": review["scope"],
              "model_turns": 0, "comparisons": "PAUSED"}
    with ReceiptStore(data["database"]) as managed, ReceiptStore(retained["ledger"]) as service:
        repo, lifecycle = AssessmentRepository(managed), AssessmentRepository(service)
        for variant in (enabled, disabled):
            PARENT["bind"](repo, data, variant)
        lifecycle.approve_budget_amendment(AssessmentBudgetAmendment.model_validate(review["service_amendment"]))
        for name, seconds in (("cleanup", 100), ("overhead", 180)):
            lifecycle.reserve(request, f"{TAG}:{name}", AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds),
                              stage="langfuse_acknowledgement_" + name)
        journey = runtime.Journey(retained, lifecycle, request, identity)
        began, nested = time.perf_counter(), 0.
        try:
            journey.inspect([runtime.PROJECT + "-" + name for name in base.SERVICES])
            journey.inspect_security()
            journey.start(*runtime.DATASTORES)
            journey.wait_datastores()
            journey.start("web", "worker")
            journey.inspect_security()
            send = runtime.carrier.docker_transport(journey.docker(), retained["containers"]["web"], journey.env)
            local = read(Path(retained["work"]) / "compose-tmpfs.json")["services"]["web"]["environment"]
            auth = "Basic " + base64.b64encode((local["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"] + ":" +
                                                local["LANGFUSE_INIT_PROJECT_SECRET_KEY"]).encode()).decode()
            definition = ReceiptExportDefinition.model_validate(read(enabled["definition"]["path"]))
            payload = PARENT["resolved"](repo, target, enabled, definition.request)
            scope = runtime.carrier.Scope(send)
            scope.permit(auth, payload, target["trace_id"])

            def cli(variant, stage, approval=None, local_auth=None):
                nonlocal nested
                clock = time.perf_counter()
                try:
                    return PARENT["cli"](profiles, variant, DOMAIN, target["receipt_id"], stage, approval, local_auth)
                finally:
                    nested += time.perf_counter() - clock

            with runtime.carrier.listen(base.PORT, scope):
                def poll(*args, **kwargs):
                    return base.Journey.poll(journey, *args, **kwargs)

                assert poll(runtime.carrier.HEALTH, attempts=8)
                result.update(exercise(cli, scope, poll, target, enabled, disabled, auth))
            if result["acknowledgement"]:
                receipt = repo.get("toolkit_receipt_export_transport", result["acknowledgement"])
                assert content_digest(receipt) == result["acknowledgement"] and receipt["execution_success"]
                result["acknowledgement_kind"] = receipt["metadata"]["acknowledgement"]
            result["passed"] = (result.get("acknowledgement_kind") == "langfuse-4.55.0-queue"
                                and result["ingestion"] and result["disablement"] and result["posts"] == 1)
        except Exception as error:
            result["error_type"] = type(error).__name__
        finally:
            try:
                journey.stop_owned()
                lifecycle.finish_operation(TAG + ":cleanup", elapsed_seconds=journey.cleanup_seconds)
                result["cleanup_verified"] = True
            except Exception as error:
                result.update(cleanup_verified=False, cleanup_error_type=type(error).__name__)
            lifecycle.finish_operation(TAG + ":overhead",
                                       elapsed_seconds=max(0., time.perf_counter() - began - journey.child_seconds - nested))
            for key, ledger, name, allowance in (
                ("service", lifecycle, request.authorization_id, MAX_SERVICE),
                ("managed", repo, "onboarding", MAX_MANAGED),
            ):
                before = review[key + "_before"]
                after = result[key + "_after"] = PARENT["counters"](ledger, name)
                assert after[0] - before[0] <= allowance and before[1] == after[1] and before[3] == after[3]
            result["passed"] &= result["cleanup_verified"]
            save(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--execute-approved")
    args = parser.parse_args()
    if args.execute_approved is None:
        validate(args.review)
        print(json.dumps({"review_sha256": sha(args.review), "validated": True, "executed": False}))
    else:
        identity = sha(args.review)
        assert args.execute_approved == identity
        assert read(args.review.with_name("operator-approval.json")) == {"approved": True, "review_sha256": identity}
        result = execute(args.review, identity)
        print(json.dumps(result, indent=2))
        sys.exit(not result["passed"])
