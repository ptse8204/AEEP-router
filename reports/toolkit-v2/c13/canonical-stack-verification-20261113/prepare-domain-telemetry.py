"""Prepare both CLI configurations with exact historical campaign and export bindings."""

import argparse
import hashlib
import json
import shutil
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from aeep.assessment.models import AssessmentPlan, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import Manifest, StrictModel
from aeep.store import ReceiptStore
from aeep.telemetry import receipt_otlp_preview
from aeep_toolkit.cli import main as cli
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition, campaign_receipt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
PREVIOUS = C13 / "langfuse-ingestion-readback-20261105/operation-review.json"
OPERATOR_WORKFLOW = ROOT / ".aeep/skillsbench-workflow-runtime-20261105/operator-workflow.json"
PREFIX = C13 / "skillsbench-software-substitute-20261109/managed-preparation/managed-engineering/operation-review.json"


class DeploymentBinding(StrictModel):
    prior_review_sha256: str
    native_service_namespace: str
    port: int
    fixed_purpose: str


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    return {"path": str(path), "sha256": sha(path)}


def check_cli(arguments):
    stdout = StringIO()
    with redirect_stdout(stdout):
        assert cli(arguments) == 0
    return json.loads(stdout.getvalue())


def prepare(work):
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    work.mkdir(mode=0o700)
    source = verification_source_digest(ROOT)
    ancestor = read(PREVIOUS)
    deployment = DeploymentBinding(
        prior_review_sha256=sha(PREVIOUS), native_service_namespace="aeep-langfuse-loopback-20261105",
        port=39067, fixed_purpose="two original SkillsBench trial-receipt traces, private loopback only",
    )
    route = read(OPERATOR_WORKFLOW)
    outcomes = read(HERE / "skillsbench-engineering-outcomes.json")
    database = Path(read(PREFIX)["database"])
    manifest = Manifest(database=str(database))
    local_manifest = work / "manifest.json"
    # These observations resolve settled attempt stores. They never start a job.
    manifest_ref = save(local_manifest, manifest.model_dump(mode="json"))
    config_refs = {}
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        for domain, selected in route["configurations"].items():
            task, = selected["task_ids"]
            row, = [item for item in outcomes["domains"][domain] if item["task_id"] == task]
            plan = AssessmentPlan.model_validate_json(Path(selected["assessment"]["plan"]["path"]).read_bytes())
            assert content_digest(plan) == content_digest(repo.get("plan", row["plan_id"]))
            report_ref = content_digest(repo.get("report", row["report_id"]))
            definition_id = "skillsbench-domain-telemetry-" + domain + "-" + source[:12]
            request = RecipeMaterializationRequest(
                plan_id=definition_id, authorization_id=plan.authorization_id,
                subject_digest=plan.subject_digest, recipe_digest=plan.recipe_digest,
                mapping_digest=plan.mapping_digest, environment_digest=plan.environment_digest,
                definition_digests=list(dict.fromkeys([plan.recipe_digest, plan.mapping_digest, plan.environment_digest])),
                seed=0,
            )
            definition = ReceiptExportDefinition(
                schema_version="aeep.toolkit.receipt-export.v2", request=request, port=39067,
                enabled=True, deployment_review_ref=content_digest(deployment), assessment_report_ref=report_ref,
            )
            receipt = campaign_receipt(repo, report_ref, row["receipt_id"], plan, request)
            assert content_digest(receipt) == row["receipt_ref"]
            otlp = receipt_otlp_preview(receipt)
            span = otlp["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
            assert otlp["receipt_sha256"] == row["receipt_ref"]
            for item in span["attributes"]:
                if item["key"] == "aeep.evidence.trust":
                    item["value"] = {"stringValue": "canonical_store_receipt"}
            common = selected | {"components": [*selected["components"],"opentelemetry","langfuse"]}
            items = []
            for name, state in (("enabled", definition),("disabled",definition.model_copy(update={"enabled":False}))):
                prefix = domain + "-" + name
                binding = save(work / f"{prefix}-export.json", state.model_dump(mode="json"))
                entry = common | {"telemetry":binding}
                workflow = save(work / f"{prefix}-workflow.json",route | {"configurations":{domain:entry}})
                accounting = WorkflowAccountingDefinition(
                    schema_version="aeep.toolkit.workflow-accounting.v2",workflow_sha256=workflow["sha256"],
                    configurations=(domain,),operations=("report",),source_digest=source,
                    manifest_path=manifest_ref["path"],manifest_sha256=manifest_ref["sha256"],request=request,
                    maximum_overhead_seconds=45,
                )
                scope = save(work / f"{prefix}-accounting.json", accounting.model_dump(mode="json"))
                preview = check_cli(["workflow","export-telemetry","--workflow",workflow["path"],
                     "--configuration",domain,"--receipt-id",receipt.receipt_id])
                assert preview["definition_ref"]==content_digest(state) and preview["enabled"]==state.enabled
                assert not preview["export_performed"]
                items.append({"workflow":workflow,"definition":binding,"definition_ref":content_digest(state),
                              "accounting":scope,"accounting_ref":content_digest(accounting),"enabled":state.enabled})
            config_refs[domain] = {
                "task":task,"report_ref":report_ref,"receipt_id":receipt.receipt_id,
                "source_receipt_sha256":row["receipt_ref"],"trace_id":span["traceId"],"span_id":span["spanId"],
                "minimized_payload_sha256":content_digest(otlp["payload"]),"variants":items,
            }
    return {"implementation_source":source,"database":str(database),"manifest":manifest_ref,
            "deployment":deployment.model_dump(mode="json"),"deployment_ref":content_digest(deployment),
            "previous_local_deployment_review":sha(PREVIOUS),"retained_service_count":len(ancestor["lifecycle"]["restart_exact_retained_services"]),
            "configurations":config_refs,"models":0,"exports_started":0,
            "status":"OFFLINE_PREPARATION_ONLY; live service review required","comparisons":"PAUSED"}


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("work",type=Path)
    print(json.dumps(prepare(parser.parse_args().work.resolve()),indent=2))
