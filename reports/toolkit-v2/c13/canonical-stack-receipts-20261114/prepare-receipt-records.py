"""Build exact stack evidence bindings from reviewed, retained operations."""

import argparse
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import REQUIRED_CHECKS, source_revisions
from aeep_toolkit.stack_receipts import StackReceiptEvidence, verify_receipt_evidence

root = Path(__file__).resolve().parents[4]
w = root / ".aeep/workflow-evidence-20261114"
review = w / "langfuse-operation-review.json"
data = json.loads(review.read_bytes())
bindings = json.loads(Path(data["bindings"]).read_bytes())
parent = json.loads(Path(data["service_review"]).read_bytes())
result = (
    root / "reports/toolkit-v2/c13/canonical-stack-verification-20261114/langfuse-live-result.json"
).resolve()
obs = json.loads(result.read_bytes())


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


links = {
    ("disabled" if k == "disabled_export" else k): {
        key: rec[key] for key in ("operation_id", "receipt_ref")
    }
    for k, rec in obs["settled_evidence"].items()
}
links.update(
    store=parent["retained_runtime"]["ledger"],
    disabled_workflow=next(
        x["workflow"]
        for x in bindings["configurations"]["document-excel"]["variants"]
        if not x["enabled"]
    ),
    observation_review=pin(review),
    observed_result=pin(result),
)
source = verification_source_digest(root)
sponsors = json.loads(
    (
        root / "reports/toolkit-v2/c13/canonical-stack-verification-20261113/sponsors-result.json"
    ).read_bytes()
)


def load(path):
    return json.loads(path.read_bytes())


def link(receipt):
    return {"operation_id": receipt["decision_id"], "receipt_ref": content_digest(receipt)}


c13 = root / "reports/toolkit-v2/c13"


def prepare(store, record_directory):
    revisions = source_revisions(source)
    verdicts = {}

    def make(name, original, proof):
        return StackReceiptEvidence(
            component=name,
            implementation_source=source,
            source_revision=revisions[name],
            original_source=original,
            compatibility_basis=(
                "Validated exact retained records, original scope, and reviewed runtime identity. "
                "This source changes readiness verification and evidence registration only. "
                "Each original source and upstream revision remains bound."
            ),
            proof=proof,
        )

    def observe(repo, evidence):
        component = evidence.component
        try:
            checks = verify_receipt_evidence(repo, evidence, component=component, source=source)
        except ConfigurationError as error:
            verdicts[component] = {"blocked": str(error)}
            return
        if set(checks) != set(REQUIRED_CHECKS[component]):
            raise RuntimeError(f"incomplete result for {component}")
        ref = content_digest(evidence)
        (record_directory / f"{component}-record.json").write_text(
            evidence.model_dump_json(indent=2) + "\n"
        )
        verdicts[component] = {
            "record_ref": ref,
            "original_source": evidence.original_source,
            "source_revision": evidence.source_revision,
            "checks": checks,
        }

    with ReceiptStore(store, read_only=True) as original:
        repo = AssessmentRepository(original)
        ref = content_digest(
            repo.get("toolkit_receipt_export_record", links["transport"]["operation_id"])
        )
        for name in ("langfuse", "semantic-conventions", "github-sponsors"):
            proof = {
                "kind": "telemetry",
                "configuration": "document-excel",
                "export_record_ref": ref,
                "receipts": links,
            }
            if name == "github-sponsors":
                proof = {
                    "kind": "sponsors",
                    "integration_evidence_ref": sponsors["record"]["integration_evidence_ref"],
                }
            evidence = make(
                name,
                sponsors["component"]["implementation_source"]
                if name == "github-sponsors"
                else data["implementation_source"],
                proof,
            )
            observe(repo, evidence)
        scanner = c13 / "scanner-fixture-continuation-20261103"
        scan = load(scanner / "cli-execution/scan.json")
        scanner_db = load(scanner / "cli-manifest.json")["database"]
        with ReceiptStore(scanner_db, read_only=True) as scanstore:
            wrapper = AssessmentRepository(scanstore).get(
                "toolkit_workflow_receipt", scan["wrapper_operation_id"]
            )
        proof = dict(
            kind="scanner",
            store=scanner_db,
            scan_ref=scan["scan_ref"],
            configuration="document-data",
            workflow=pin(scanner / "cli-workflow.json"),
            wrapper=link(wrapper),
        )
        name = "skill-scanner"
        observe(repo, make(name, scan["implementation_source"], proof))
        for name in ("mcpmark", "mcp-universe"):
            folder = c13 / (name + "-postgres-tool-schema-20261105")
            result = folder / "execution"
            review = load(folder / "operation-review.json")
            proof = dict(
                kind="mcp_reference",
                review=pin(folder / "operation-review.json"),
                prepared=pin(folder / "prepared.json"),
                result=pin(result / "summary.json"),
                receipts={
                    n: link(load(result / (n + ".json")))
                    for n in (
                        "seed-start",
                        "missing-start",
                        "execute-sql",
                        "reference-start",
                        "db-stopped",
                        "server-stopped",
                    )
                },
            )
            observe(repo, make(name, review["source"], proof))
        name = "toolhive"
        folder = c13 / "toolhive-loopback-bind-20261104"
        rev = load(folder / "operation-review.json")
        proof = dict(
            kind="toolhive",
            review=pin(folder / "operation-review.json"),
            result=pin(folder / "summary.json"),
            boundary=pin(folder / "server-boundary.json"),
            listener=pin(folder / "listener-verdict.json"),
            receipts={
                n: link(load(folder / ("receipt-" + n + ".json")))
                for n in (
                    "foreground-service",
                    "verify-loopback-listener",
                    "container-inspect",
                    "boundary-call",
                    "aeep-client",
                    "stopped-inspect-discover",
                )
            },
        )
        observe(repo, make(name, rev["source"], proof))
        name = "skillrank"
        old = c13 / "canonical-stack-verification-20261113/skillrank-ledger-audit.json"
        audit = load(old)
        info = audit["search_show"]
        proof = dict(
            kind="skillrank",
            catalog_store=links["store"],
            catalog_source=info[0]["original_source"],
            search_ref=info[0]["catalog_ref"],
            show_ref=info[1]["catalog_ref"],
            diagnostic_report_ref=audit["bounded_diagnostic"]["report_ref"],
        )
        observe(repo, make(name, audit["bounded_diagnostic"]["original_source"], proof))
        name = "agent-skill-eval"
        audit = load(c13 / "integration-snapshot-correction-20261103/completion-audit.json")
        proof = dict(
            kind="scheduled",
            report_ref=content_digest(repo.get("report", audit["rows"][0]["canonical_report_id"])),
        )
        observe(repo, make(name, audit["source"], proof))

        name = "aeep-evaluator"
        audit = load(c13 / "integration-snapshot-correction-20261103/completion-audit.json")
        recovery = c13 / "repository-usefulness-pilot-20261029/stopped-accounting-audit.json"
        recovery_ref = load(recovery)[
            "unused_report_reservation_settled_from_verified_unstarted_body"
        ]["recovery_record_digest"]
        proof = dict(
            kind="managed",
            report_ref=content_digest(repo.get("report", audit["rows"][1]["canonical_report_id"])),
            recovery_ref=recovery_ref,
            recovery_source=load(recovery)[
                "unused_report_reservation_settled_from_verified_unstarted_body"
            ]["source_digest"],
            recovery_audit=pin(recovery),
        )
        observe(repo, make(name, audit["source"], proof))
        name = "skillsbench"
        audit = load(c13 / "canonical-stack-verification-20261113/skillsbench-ledger-audit.json")
        runtime_root = root / ".aeep"
        doc = runtime_root / "skillsbench-document-rights-20261106"
        workflow = runtime_root / "skillsbench-sales-handoff-20261105/sales-prepared/workflow.json"
        shared = Path(load(workflow)["configurations"]["document-data"]["benchmark"]["path"])
        packs = [
            shared,
            doc / "invoice-fraud-detection-bound-pack.json",
            doc / "exceltable-in-ppt-bound-pack.json",
            shared,
            runtime_root
            / "skillsbench-react-managed-preparation-20261107/react-performance-debugging-bound-pack.json",
            runtime_root
            / "skillsbench-software-substitute-20261109/managed-preparation/cli-definitions/pack.json",
        ]
        verifiers = {}
        for name_suffix, task in (
            ("sales-protected-grading", "sales-pivot-analysis"),
            ("spring-offline-reference", "spring-boot-jakarta-migration"),
        ):
            control = c13 / ("skillsbench-" + name_suffix + "-20261105")
            result = control / "execution"
            verifiers[task] = dict(
                review=pin(control / "operation-review.json"),
                reference=link(load(result / "reference-start.json")),
                negative=link(load(result / "missing-start.json")),
                reference_result=pin(result / "reference-verdict.json"),
                negative_result=pin(result / "missing-verdict.json"),
            )
        proof = dict(
            kind="skillsbench",
            verifier_store=links["store"],
            runs={
                row["task_id"]: dict(
                    report_ref=row["report_ref"],
                    original_source=row["implementation_source"],
                    pack=pin(path),
                )
                for row, path in zip(audit["observations"], packs, strict=True)
            },
            verifiers=verifiers,
        )
        observe(repo, make(name, audit["observations"][0]["implementation_source"], proof))
        for name, rel, leaf, outer, inner in (
            (
                "langgraph",
                "workflow-accounting-20261101/composed-sdk-runtime",
                "langgraph-sdk.json",
                "langgraph-sdk-receipt.json",
                "owned-work/canonical.sqlite3",
            ),
            (
                "agent-framework",
                "workflow-lifecycle-20261102/corrected-sdk-runtime",
                "framework-component-result.json",
                "framework-component-receipt.json",
                "owned-work/framework/canonical.sqlite3",
            ),
        ):
            d = c13 / rel
            regular = d / "execution"
            review = d / "operation-review.json"
            receipt = load(regular / outer)
            proof = dict(
                kind="sdk",
                review=pin(review),
                result=pin(regular / leaf),
                process_store=str(regular / "outer-receipts.sqlite3"),
                process_receipt_id=receipt["receipt_id"],
                process_receipt_ref=content_digest(receipt),
                step_store=str(regular / inner),
            )
            observe(repo, make(name, load(review)["checkout_source"], proof))
        for name, rel, output in (
            ("evoagentx", "evoagentx-distribution-20261106/managed-turn", "reconciled-result.json"),
            (
                "aflow",
                "proposal-optimizer-preparation-20261105/calibration/finite-cycle",
                "result.json",
            ),
        ):
            folder = c13 / rel
            review = folder / "operation-review.json"
            result = folder / output
            proof = dict(
                kind="proposal",
                review=pin(review),
                result=pin(result),
                validator=link(load(folder / "validation-receipt.json")),
            )
            observe(repo, make(name, load(review)["source_sha256"], proof))
        name = "aeep-router"
        folder = c13 / "optional-router-20261104"
        r = folder / "operation-review.json"
        proof = dict(
            kind="router",
            review=pin(r),
            result=pin(folder / "summary.json"),
            store=load(r)["work"] + "/state.db",
        )
        observe(repo, make(name, load(r)["source"], proof))

    verdicts["waza"] = {
        "blocked": "Supported backend sign-in and live protected grade are missing."
    }
    return {"implementation_source": source, "components": verdicts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    print(json.dumps(prepare(args.store, args.output), indent=2, allow_nan=False))
