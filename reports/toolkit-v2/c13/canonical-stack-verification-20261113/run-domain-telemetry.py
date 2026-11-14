"""Bound two ordinary CLI exports to a retained private Langfuse lifecycle."""

import argparse
import base64
import hashlib
import json
import runpy
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentLimits, AssessmentPlan, AssessmentScopeAmendment,
    RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep.store import ReceiptStore
from aeep.telemetry import receipt_otlp_preview
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition, campaign_receipt

HERE = Path(__file__).resolve().parent
C13 = HERE.parent
CHECK = runpy.run_path(str(HERE / "preflight-langfuse-domain.py"))
DEFINITIONS = runpy.run_path(str(HERE / "prepare-domain-telemetry.py"))
runtime, base = CHECK["runtime"], CHECK["base"]
read, sha = CHECK["read"], CHECK["sha"]
PREVIOUS = CHECK["PRIOR"] / "operation-review.json"
TAG = "skillsbench-domain-telemetry-20261113"


def counters(repo, identity):
    return list(repo.store._connection.execute(
        "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?", (identity,),
    ).fetchone())


def save(path, data):
    with path.open("x") as out:
        json.dump(data, out, indent=2)
        out.write("\n")


def review_output(profile_dir, output):
    old = read(PREVIOUS)
    preflight = CHECK["audit"]()
    assert not output.exists() and profile_dir.is_dir()
    definitions = read(HERE / "domain-telemetry-preflight.json")
    identity = old["grant_authorization_id"]
    with ReceiptStore(old["ledger"], read_only=True) as store:
        repo = AssessmentRepository(store)
        before = counters(repo, identity)
        root = repo.get("authorization", identity)
        limits = repo.effective_grant(identity).limits
        prior, = store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='budget_amendment' "
            "AND json_extract(payload_json,'$.authorization_id')=? ORDER BY rowid DESC LIMIT 1",
            (identity,),
        ).fetchone()
        assert before == preflight["counters"] and limits.max_cash_usd == 0
    with ReceiptStore(definitions["database"], read_only=True) as store:
        managed_before = counters(AssessmentRepository(store), "onboarding")
    amended = AssessmentBudgetAmendment(
        amendment_id=TAG, authorization_id=identity, authorization_digest=content_digest(root),
        previous_amendment_digest=prior, limits=limits.model_copy(update={"max_operations":before[0]+50}),
        expires_at=utc_now()+timedelta(days=2), issued_at=utc_now(),
    )
    pins = {str(path):sha(path) for path in (
        Path(__file__), PREVIOUS, HERE/"preflight-langfuse-domain.py", HERE/"prepare-domain-telemetry.py",
        HERE/"domain-telemetry-preflight.json", CHECK["PRIOR"]/"run.py", runtime.__file__,
        C13/"langfuse-loopback-carrier-20261105"/"relay.py", *[profile_dir/name for name in ("entry.py","enabled.sb","disabled.sb")],
    )}
    for config in definitions["configurations"].values():
        for v in config["variants"]:
            for k in ("workflow", "definition", "accounting"):
                assert sha(v[k]["path"]) == v[k]["sha256"]
                pins[v[k]["path"]] = v[k]["sha256"]
    manifest = definitions["manifest"]
    assert sha(manifest["path"]) == manifest["sha256"]
    pins[manifest["path"]] = manifest["sha256"]
    retained = old | {
        "expires_at": amended.expires_at.isoformat(),
        "maximum_driver_commands": 30,
        "executables": {path:sha(Path(path).resolve()) for path in old["executables"]},
    }
    base.validate(retained)
    review = {
        "purpose":"Restart only the reviewed private Langfuse containers and verify two exact domain traces",
        "implementation_source":definitions["implementation_source"],"owned_output":str(output),"profiles":str(profile_dir),
        "pins":pins,"service_amendment":amended.model_dump(mode="json"),"retained_runtime":retained,
        "service_grant_before":before,"managed_grant_before":managed_before,"scope":preflight["trace_bindings"],
        "retained_namespace":preflight["retained_namespace"],"retained_services":list(runtime.LIVE),
        "maximum_additional_service_operations":50,"maximum_additional_managed_operations":10,
        "maximum_managed_reserved_seconds":600,"existing_service_absolute_reserved_seconds":limits.max_elapsed_seconds,
        "maximum_posts":2,"maximum_readbacks_per_trace":8,"maximum_model_turns":0,"maximum_cash_usd":"0",
        "new_resources":False,"deletion":False,"automatic_retry":False,"comparisons":"PAUSED",
    }
    # Exercise exact definition review and canonical receipt checks on an isolated copy.
    with ReceiptStore(definitions["database"], read_only=True) as live, ReceiptStore(":memory:") as copy:
        live._connection.backup(copy._connection)
        for target in definitions["configurations"].values():
            for variant in target["variants"]:
                scope = bind(AssessmentRepository(copy), definitions, variant)
                resolved(AssessmentRepository(copy),target,variant,scope.request)
    return review


def bind(repo, definitions, variant):
    runtime_def = ReceiptExportDefinition.model_validate(read(variant["definition"]["path"]))
    scope = WorkflowAccountingDefinition.model_validate(read(variant["accounting"]["path"]))
    deployment = DEFINITIONS["DeploymentBinding"].model_validate(definitions["deployment"])
    deploy_ref = repo.put("toolkit_receipt_export_deployment", content_digest(deployment), deployment)
    assert deploy_ref == runtime_def.deployment_review_ref and scope.request == runtime_def.request
    assert content_digest(scope) == variant["accounting_ref"]
    assert content_digest(runtime_def) == variant["definition_ref"]
    request = scope.request
    refs = {
        request.subject_digest:"subject",request.recipe_digest:"recipe",
        request.mapping_digest:"mapping",request.environment_digest:"environment",
        repo.put("toolkit_receipt_export",content_digest(runtime_def),runtime_def):"toolkit_receipt_export",
        repo.put("toolkit_workflow_accounting",content_digest(scope),scope):"toolkit_workflow_accounting",
        deploy_ref:"toolkit_receipt_export_deployment",
    }
    for ref in refs:
        status = repo.store._connection.execute("SELECT revoked FROM assessment_reviews WHERE digest=?", (ref,)).fetchone()
        assert status is None or not status[0]
    amendment = AssessmentScopeAmendment(
        amendment_id=request.plan_id + ("-on" if runtime_def.enabled else "-off"),
        authorization_id=request.authorization_id,authorization_digest=content_digest(repo.get("authorization",request.authorization_id)),
        subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest],reviewed_digests=list(refs),
    )
    repo.approve_bundle(amendment,{ref:repo.get(kind,ref) for ref,kind in refs.items()})
    repo.authorize(request)
    return scope


def resolved(repo,target,variant,request):
    workflow = read(variant["workflow"]["path"])
    selected, = workflow["configurations"].values()
    plan = AssessmentPlan.model_validate(read(selected["assessment"]["plan"]["path"]))
    original = campaign_receipt(repo,target["report_ref"],target["receipt_id"],plan,request)
    preview = receipt_otlp_preview(original)
    span = preview["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    for attribute in span["attributes"]:
        if attribute["key"] == "aeep.evidence.trust":
            attribute["value"] = {"stringValue":"canonical_store_receipt"}
    assert preview["receipt_sha256"] == target["source_receipt_sha256"]
    assert (span["traceId"],span["spanId"]) == (target["trace_id"],target["span_id"])
    assert content_digest(preview["payload"]) == target["minimized_payload_sha256"]
    return preview["payload"]


def cli(profiles,variant,domain,receipt,stage,approval=None,auth=None):
    enabled = variant["enabled"]
    profile = profiles / ("enabled.sb" if enabled else "disabled.sb")
    command = ["/usr/bin/sandbox-exec","-f",str(profile),str(Path(sys.executable).resolve()),"-I","-B",str(profiles/"entry.py"),
        "workflow","export-telemetry","--workflow",variant["workflow"]["path"],"--configuration",domain,
        "--receipt-id",receipt,"--accounting",variant["accounting"]["path"],"--operation-id",stage]
    env = {"PATH":"/usr/bin:/bin","HOME":str(profiles/"home"),"TMPDIR":str(profiles/"tmp"),"LC_ALL":"C"}
    if approval:
        command += ["--reviewed-digest",approval]
    if auth:
        assert enabled and approval
        env["AEEP_LANGFUSE_LOCAL_AUTH"] = auth
    run = subprocess.run(command,env=env,cwd=profiles,capture_output=True,timeout=60)
    assert run.returncode == 0, ("export CLI stopped",stage,hashlib.sha256(run.stderr).hexdigest())
    return json.loads(run.stdout)


def execute(review,identity):
    definitions = read(HERE / "domain-telemetry-preflight.json")
    retained = review["retained_runtime"]
    profiles, output = Path(review["profiles"]), Path(review["owned_output"])
    assert CHECK["audit"]()["trace_bindings"] == review["scope"]
    assert verification_source_digest(CHECK["ROOT"]) == review["implementation_source"]
    assert all(sha(p) == d for p,d in review["pins"].items())
    base.validate(retained)
    output.mkdir(mode=0o700)
    base.HERE = output
    (output/"service-execution").mkdir(mode=0o700)
    save(output/"started.json",{"review_sha256":identity,"comparisons":"PAUSED"})
    manifest = read(runtime.PRIOR / "prepared.json")
    request = RecipeMaterializationRequest.model_validate(manifest["request"]).model_copy(update={"plan_id":TAG})
    amended = AssessmentBudgetAmendment.model_validate(review["service_amendment"])
    results = {"passed":False,"models":0,"comparisons":"PAUSED","review_sha256":identity,"domains":{}}
    with ReceiptStore(retained["ledger"]) as service, ReceiptStore(definitions["database"]) as managed:
        lifecycle, repository = AssessmentRepository(service), AssessmentRepository(managed)
        assert counters(lifecycle,request.authorization_id) == review["service_grant_before"]
        assert counters(repository,"onboarding") == review["managed_grant_before"]
        for config in definitions["configurations"].values():
            for variant in config["variants"]:
                bind(repository,definitions,variant)
        lifecycle.approve_budget_amendment(amended)
        reserved = {label:TAG+":"+label for label in ("cleanup","overhead")}
        for label, seconds in (("cleanup",100),("overhead",240)):
            lifecycle.reserve(request,reserved[label],AssessmentLimits(max_operations=1,max_elapsed_seconds=seconds),
                              stage="langfuse_domain_"+label)
        journey = runtime.Journey(retained,lifecycle,request,identity)
        started = time.perf_counter()
        nested = 0.
        phase = "owned startup"
        try:
            journey.inspect([runtime.PROJECT+"-"+name for name in base.SERVICES])
            journey.inspect_security()
            journey.start(*runtime.DATASTORES)
            journey.wait_datastores()
            journey.start("web","worker")
            journey.inspect_security()
            send = runtime.carrier.docker_transport(journey.docker(),retained["containers"]["web"],journey.env)
            # The existing private deployment file contains only task-owned local service keys.
            local = read(Path(retained["work"])/"compose-tmpfs.json")["services"]["web"]["environment"]
            auth = "Basic "+base64.b64encode((local["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"]+":"+
                    local["LANGFUSE_INIT_PROJECT_SECRET_KEY"]).encode()).decode()
            for domain,target in definitions["configurations"].items():
                phase = domain+" exact export"
                selected, = [v for v in target["variants"] if v["enabled"]]
                disabled, = [v for v in target["variants"] if not v["enabled"]]
                scope = WorkflowAccountingDefinition.model_validate(read(selected["accounting"]["path"]))
                payload=resolved(repository,target,selected,scope.request)
                carrier=runtime.carrier.Scope(send)
                carrier.permit(auth,payload,target["trace_id"])
                with runtime.carrier.listen(base.PORT,carrier):
                    # The carrier subclass installs a listener in its health
                    # method. This journey already owns the exact payload listener.
                    assert base.Journey.poll(journey,runtime.carrier.HEALTH,attempts=10)
                    def accounted_cli(variant, stage, approved=None, local_auth=None):
                        nonlocal nested
                        began = time.perf_counter()
                        try:
                            return cli(profiles,variant,domain,target["receipt_id"],stage,approved,local_auth)
                        finally:
                            nested += time.perf_counter() - began
                    disabled_preview=accounted_cli(disabled,"disabled-preview")
                    disabled_result=accounted_cli(disabled,"disabled",disabled_preview["review_sha256"])
                    assert disabled_result["status"]=="disabled" and carrier.counts["export"]==0
                    preview=accounted_cli(selected,"enabled-preview")
                    assert preview["payload_sha256"]==target["minimized_payload_sha256"]
                    export_error=None
                    try:
                        export=accounted_cli(selected,"export",preview["review_sha256"],auth)
                    except AssertionError as error:
                        export_error=str(error)
                        export=None
                    assert carrier.counts["export"]==1
                    assert journey.poll("/api/public/v2/observations",expected=target,auth=auth,attempts=8)
                    results["domains"][domain]={"trace_id":target["trace_id"],"span_id":target["span_id"],
                        "source_receipt_sha256":target["source_receipt_sha256"],"ingestion_verified":True,
                        "disabled_export_verified":True,"post_invocations":carrier.counts["export"],
                        "transport_record":export,"transport_exit":export_error}
            results["passed"]=len(results["domains"])==2
        except Exception as error:
            results.update(stopped_phase=phase,error_type=type(error).__name__)
        finally:
            try:
                journey.stop_owned()
                lifecycle.finish_operation(reserved["cleanup"],elapsed_seconds=journey.cleanup_seconds)
                results["cleanup_verified"]=True
            except Exception as error:
                results.update(cleanup_verified=False,cleanup_error_type=type(error).__name__)
            lifecycle.finish_operation(reserved["overhead"],elapsed_seconds=max(0.,time.perf_counter()-started-journey.child_seconds-nested))
            results["service_grant_after"]=counters(lifecycle,request.authorization_id)
            results["managed_grant_after"]=counters(repository,"onboarding")
            assert results["service_grant_after"][0]-review["service_grant_before"][0]<=50
            assert results["managed_grant_after"][0]-review["managed_grant_before"][0]<=10
            assert results["managed_grant_after"][1]==review["managed_grant_before"][1]
            results["passed"] &= results["cleanup_verified"]
            save(output/"result.json",results)
    return results


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("review",type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare",nargs=2,type=Path,metavar=("PROFILES","OUTPUT"))
    mode.add_argument("--execute-approved")
    args=parser.parse_args()
    if args.prepare:
        save(args.review,review_output(*(path.resolve() for path in args.prepare)))
        print(sha(args.review))
    else:
        identity=sha(args.review)
        assert identity==args.execute_approved
        assert read(args.review.with_name("operator-approval.json"))=={"approved":True,"review_sha256":identity}
        result=execute(read(args.review),identity)
        print(json.dumps(result,indent=2))
        raise SystemExit(not result["passed"])
