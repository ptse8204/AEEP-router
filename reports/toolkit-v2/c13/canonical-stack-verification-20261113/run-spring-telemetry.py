"""Continue the unstarted Spring export without replaying Sales telemetry."""

import argparse
import base64
import json
import runpy
import socket
import time
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition, accepted
from aeep.models import ExecutionStatus, RawExecution

HERE = Path(__file__).resolve().parent
PARENT = runpy.run_path(str(HERE / "run-domain-telemetry.py"))
read, sha, save = (PARENT[key] for key in ("read", "sha", "save"))
runtime, base = PARENT["runtime"], PARENT["base"]
TAG = "skillsbench-spring-telemetry-20261113"
DOMAIN = "software-engineering"
REPORT = HERE / "domain-live-result.json"
DEFINITIONS = HERE / "domain-telemetry-preflight.json"


def binding(definitions):
    target = definitions["configurations"][DOMAIN]
    selected, = [variant for variant in target["variants"] if variant["enabled"]]
    disabled, = [variant for variant in target["variants"] if not variant["enabled"]]
    definition = ReceiptExportDefinition.model_validate(read(selected["definition"]["path"]))
    operation = f"receipt-export:{content_digest(definition)}:{target['source_receipt_sha256']}"
    return target, selected, disabled, operation


def require_unstarted(repository, operation, selected):
    request = WorkflowAccountingDefinition.model_validate(read(selected["accounting"]["path"])).request
    rows = repository.store._connection.execute(
        "SELECT 1 FROM assessment_operations WHERE id=? OR id LIKE ?",
        (operation, "workflow:" + request.plan_id + ":%"),
    ).fetchone()
    assert rows is None
    return request


def preflight(review):
    old = read(review["parent_review"])
    assert sha(review["parent_review"]) == review["parent_review_sha256"]
    assert not Path(review["owned_output"]).exists()
    assert all(sha(file) == digest for file, digest in review["pins"].items())
    assert all(sha(file) == digest for file, digest in old["pins"].items())
    assert verification_source_digest(PARENT["CHECK"]["ROOT"]) == old["implementation_source"]
    retained = old["retained_runtime"]
    base.validate(retained)
    ids = [retained["containers"][name] for name in base.SERVICES]
    observed = runtime.safe_read(retained, "inspect", "--format", runtime.STATE_TEMPLATE, *ids)
    for name, line in zip(base.SERVICES, observed.splitlines(), strict=True):
        ident, state, status, labels = tuple(runtime.decode(line))
        assert ident == retained["containers"][name] and state == "exited"
        assert labels[base.LABEL] == runtime.PROJECT and labels["com.docker.compose.service"] == name
        if name not in runtime.LIVE:
            assert status == 0
    assert runtime.check_permissions(retained, ids)
    with socket.socket() as test_listener:
        test_listener.bind(("127.0.0.1", base.PORT))
    definitions = read(DEFINITIONS)
    target, selected, _, operation = binding(definitions)
    assert operation == review["export_operation"] and target["trace_id"] == review["trace_id"]
    historical = read(REPORT)
    assert historical["cleanup_verified"] and historical["software_dispatch_observation"] == "UNSTARTED"
    assert historical["domains"]["document-data"]["ingestion_verified"]
    with ReceiptStore(retained["ledger"], read_only=True) as service, ReceiptStore(
            definitions["database"], read_only=True) as managed:
        lifecycle, repository = AssessmentRepository(service), AssessmentRepository(managed)
        assert PARENT["counters"](lifecycle, retained["grant_authorization_id"]) == review["service_before"]
        assert PARENT["counters"](repository, "onboarding") == review["managed_before"]
        assert not service._connection.execute(
            "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",
            (retained["grant_authorization_id"],),
        ).fetchone()
        request = require_unstarted(repository, operation, selected)
        PARENT["resolved"](repository, target, selected, request)
        grant = lifecycle.current_grant(retained["grant_authorization_id"])
        assert grant.limits.max_operations >= review["service_before"][0] + review["max_service_operations"]
        assert grant.limits.max_elapsed_seconds == old["existing_service_absolute_reserved_seconds"]
        assert grant.limits.max_model_turns == grant.limits.max_cash_usd == 0
    return old, definitions


def bounded_cli(send, cli, poll, target, selected, disabled, payload, auth, port):
    observations = {}

    def observe(method, path, header, body):
        status, reply = send(method, path, header, body)
        if method == "POST":
            try:
                output = json.loads(reply)
            except ValueError:
                output = None
            observations["post_response"] = {
                "http_status": status, "bytes": len(reply), "json_object": isinstance(output, dict),
                "otlp_acceptance_valid": status == 200 and accepted(
                    RawExecution(status=ExecutionStatus.SUCCESS, output=output)
                ),
            }
        return status, reply

    carrier = runtime.carrier.Scope(observe)
    carrier.permit(auth, payload, target["trace_id"])
    with runtime.carrier.listen(port, carrier):
        assert poll(runtime.carrier.HEALTH, attempts=10)
        before = cli(disabled, "disabled-preview")
        status = cli(disabled, "disabled", before["review_sha256"])
        assert status["status"] == "disabled" and carrier.counts["export"] == 0
        observations["disabled_export_verified"] = True
        preview = cli(selected, "enabled-preview")
        assert preview["payload_sha256"] == target["minimized_payload_sha256"]
        try:
            observations["transport_record"] = cli(selected, "export", preview["review_sha256"], auth)
        except AssertionError as error:
            observations["transport_exit"] = str(error)
        observations["post_invocations"] = carrier.counts["export"]
        observations["ingestion_verified"] = carrier.counts["export"] == 1 and poll(
            "/api/public/v2/observations",
            expected=target, auth=auth, attempts=8,
        )
        return observations


def execute(review, identity):
    old, definitions = preflight(review)
    retained = old["retained_runtime"]
    output, profiles = Path(review["owned_output"]), Path(old["profiles"])
    output.mkdir(mode=0o700)
    (output / "service-execution").mkdir(mode=0o700)
    base.HERE = output
    save(output / "started.json", {"review_sha256": identity, "models": 0})
    manifest = read(runtime.PRIOR / "prepared.json")
    request = RecipeMaterializationRequest.model_validate(manifest["request"]).model_copy(update={"plan_id": TAG})
    target, selected, disabled, operation = binding(definitions)
    results = {"passed": False, "review_sha256": identity, "comparison_dispatch": "PAUSED",
               "trace_id": target["trace_id"], "span_id": target["span_id"], "models": 0,
               "source_receipt_sha256": target["source_receipt_sha256"], "sales_replayed": False}
    with ReceiptStore(retained["ledger"]) as service, ReceiptStore(definitions["database"]) as managed:
        lifecycle, repository = AssessmentRepository(service), AssessmentRepository(managed)
        scope = require_unstarted(repository, operation, selected)
        repository.authorize(scope)
        for label, seconds in (("cleanup", 100), ("overhead", 180)):
            lifecycle.reserve(request, f"{TAG}:{label}", AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds),
                              stage="langfuse_spring_" + label)
        journey = runtime.Journey(retained, lifecycle, request, identity)
        began, nested = time.perf_counter(), 0.0
        try:
            journey.inspect([runtime.PROJECT+"-"+name for name in base.SERVICES])
            journey.inspect_security()
            journey.start(*runtime.DATASTORES)
            journey.wait_datastores()
            journey.start("web", "worker")
            journey.inspect_security()
            send = runtime.carrier.docker_transport(journey.docker(), retained["containers"]["web"], journey.env)
            local = read(Path(retained["work"]) / "compose-tmpfs.json")["services"]["web"]["environment"]
            auth = "Basic " + base64.b64encode((local["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"] + ":" +
                                                local["LANGFUSE_INIT_PROJECT_SECRET_KEY"]).encode()).decode()

            def cli(variant, stage, approval=None, local_auth=None):
                nonlocal nested
                clock = time.perf_counter()
                try:
                    return PARENT["cli"](profiles, variant, DOMAIN, target["receipt_id"], stage, approval, local_auth)
                finally:
                    nested += time.perf_counter() - clock

            payload = PARENT["resolved"](repository, target, selected, scope)
            results.update(bounded_cli(send, cli, lambda *a, **kw: base.Journey.poll(journey, *a, **kw),
                                       target, selected, disabled, payload, auth, base.PORT))
            results["passed"] = results["ingestion_verified"] and results["disabled_export_verified"]
        except Exception as error:
            results["error_type"] = type(error).__name__
        finally:
            try:
                journey.stop_owned()
                lifecycle.finish_operation(TAG+":cleanup", elapsed_seconds=journey.cleanup_seconds)
                results["cleanup_verified"] = True
            except Exception as error:
                results.update(cleanup_verified=False, cleanup_error_type=type(error).__name__)
            lifecycle.finish_operation(TAG+":overhead", elapsed_seconds=max(0., time.perf_counter()-began-journey.child_seconds-nested))
            for key, repo, grant, allowance in (
                ("service", lifecycle, retained["grant_authorization_id"], review["max_service_operations"]),
                ("managed", repository, "onboarding", review["max_managed_operations"]),
            ):
                current = PARENT["counters"](repo, grant)
                before = review[key + "_before"]
                results[key + "_after"] = current
                assert current[0]-before[0] <= allowance and current[1] == before[1] and current[3] == before[3]
            results["passed"] &= results["cleanup_verified"]
            save(output / "result.json", results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("--execute-approved")
    args = parser.parse_args()
    review, identity = read(args.review), sha(args.review)
    if args.execute_approved is None:
        preflight(review)
        print(json.dumps({"review_sha256": identity, "preflight": "PASSED", "executed": False}))
    else:
        assert args.execute_approved == identity
        assert read(args.review.with_name("spring-operator-approval.json")) == {"approved": True, "review_sha256": identity}
        result = execute(review, identity)
        print(json.dumps(result, indent=2))
        raise SystemExit(not result["passed"])
