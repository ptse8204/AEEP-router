"""Prepare a fresh receipt test; does not start Langfuse or authorize a send."""

import argparse
import json
import runpy
import shutil
from pathlib import Path

from aeep.assessment.models import AssessmentPlan, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import Manifest
from aeep.store import ReceiptStore
from aeep.telemetry import receipt_otlp_preview
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition, campaign_receipt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = runpy.run_path(str(HERE / "prepare-domain-telemetry.py"))
read, save, sha, check_cli = (OLD[name] for name in ("read", "save", "sha", "check_cli"))
DOMAIN = "document-excel"
TASK = "exceltable-in-ppt"


def stage(work):
    assert work.is_relative_to(ROOT / ".aeep") and shutil.disk_usage(ROOT).free >= 50 * 1024**3
    work.mkdir(mode=0o700)
    source = verification_source_digest(ROOT)
    original = read(HERE / "domain-telemetry-preflight.json")
    original_workflow = ROOT / ".aeep/skillsbench-document-managed-20261106/managed-execution/excel-prepared/workflow.json"
    route = read(original_workflow)
    selected = route["configurations"][DOMAIN]
    assert selected["task_ids"] == [TASK]
    manifest = save(work / "manifest.json", Manifest(database=original["database"]).model_dump(mode="json"))
    deployment = OLD["DeploymentBinding"](
        prior_review_sha256=sha(Path(OLD["PREVIOUS"])),
        native_service_namespace=original["deployment"]["native_service_namespace"],
        port=39067, fixed_purpose="one fresh receipt; Langfuse 4.55.0 queued acknowledgement and exact readback",
    )
    row, = (task for task in read(HERE / "skillsbench-engineering-outcomes.json")["domains"]["document-data"]
            if task["task_id"] == TASK)
    plan = AssessmentPlan.model_validate_json(Path(selected["assessment"]["plan"]["path"]).read_bytes())
    request = RecipeMaterializationRequest(**{
        key: getattr(plan, key) for key in ("authorization_id", "subject_digest", "recipe_digest",
                                          "environment_digest", "mapping_digest", "definition_digests")
    }, plan_id="skillsbench-langfuse-ack-" + source[:12], seed=0)
    with ReceiptStore(original["database"], read_only=True) as store:
        repo = AssessmentRepository(store)
        report_ref = content_digest(repo.get("report", row["report_id"]))
        receipt = campaign_receipt(repo, report_ref, row["receipt_id"], plan, request)
        otlp = receipt_otlp_preview(receipt)
        assert otlp["receipt_sha256"] == row["receipt_ref"]
        assert not store._connection.execute(
            "SELECT 1 FROM assessment_operations WHERE id LIKE ?",
            ("receipt-export:%:" + row["receipt_ref"],),
        ).fetchone(), "Fresh receipt required, regardless of previous definition"
    span = otlp["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    for item in span["attributes"]:
        if item["key"] == "aeep.evidence.trust":
            item["value"] = {"stringValue": "canonical_store_receipt"}
    definition = ReceiptExportDefinition(
        schema_version="aeep.toolkit.receipt-export.v3", acknowledgement="langfuse-4.55.0-queue",
        request=request, port=39067, enabled=True, deployment_review_ref=content_digest(deployment),
        assessment_report_ref=report_ref,
    )
    variants = []
    for suffix, value in (("enabled", definition), ("disabled", definition.model_copy(update={"enabled": False}))):
        def_ref = save(work / f"{suffix}-definition.json", value.model_dump(mode="json"))
        workflow = save(work / f"{suffix}-workflow.json", route | {
            "configurations": {DOMAIN: selected | {"telemetry": def_ref,
                "components": [*selected["components"], "opentelemetry", "langfuse"]}},
        })
        scope = WorkflowAccountingDefinition(
            schema_version="aeep.toolkit.workflow-accounting.v2", workflow_sha256=workflow["sha256"],
            configurations=(DOMAIN,), operations=("report",), source_digest=source,
            manifest_path=manifest["path"], manifest_sha256=manifest["sha256"], request=request,
            maximum_overhead_seconds=45,
        )
        scope_file = save(work / f"{suffix}-accounting.json", scope.model_dump(mode="json"))
        preview = check_cli(["workflow", "export-telemetry", "--workflow", workflow["path"],
                             "--configuration", DOMAIN, "--receipt-id", receipt.receipt_id])
        assert not preview["export_performed"] and preview["definition_ref"] == content_digest(value)
        variants.append({"definition": def_ref, "workflow": workflow, "accounting": scope_file,
                         "accounting_ref": content_digest(scope), "definition_ref": content_digest(value),
                         "enabled": value.enabled})
    return {
        "implementation_source": source, "database": original["database"], "manifest": manifest,
        "deployment": deployment.model_dump(mode="json"), "source_workflow_sha256": sha(original_workflow),
        "configurations": {DOMAIN: {
            "task": TASK, "report_ref": report_ref, "receipt_id": receipt.receipt_id,
            "source_receipt_sha256": row["receipt_ref"], "trace_id": span["traceId"], "span_id": span["spanId"],
            "minimized_payload_sha256": content_digest(otlp["payload"]), "variants": variants,
        }}, "status": "PREPARED_NO_DISPATCH", "comparisons": "PAUSED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    work = parser.parse_args().work.resolve()
    save(work / "bindings.json", stage(work))
