"""Bind the approved synthetic upstream batch to existing AEEP evidence storage."""

from __future__ import annotations

from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorSpec,
    SideEffect,
    StrictModel,
    utc_now,
)
from aeep.store import ReceiptStore
from aeep_toolkit.cli import read_json
from aeep_toolkit.models import (
    AdapterCapabilities,
    ComparisonReport,
    EvaluationRun,
    EvidenceBundle,
    SourcePin,
)


class FixtureRecord(StrictModel):
    """Private development records, not an authorization or production schema."""

    facts: dict


async def execute(argv: list[str], cwd: Path, env: dict, database: Path) -> tuple[str, str]:
    """Called only after stack.py validates the pinned fixture and sandbox probes."""
    spec = ExecutorSpec(
        id="toolkit.fixture.coordinator", capability="toolkit.fixture.batch", kind="command",
        description="Pinned agent-skill-eval synthetic coordinator; no model execution",
        input_schema={"type": "object", "additionalProperties": False},
        side_effect=SideEffect.WRITE, idempotent=False,
        config={"argv": argv, "argv_literal": True, "cwd": str(cwd), "env": env,
                "inherit_env": False, "timeout_seconds": 120, "max_output_bytes": 1000000},
    )
    request = ActionRequest(capability=spec.capability, input={})
    started = utc_now()
    executor = CommandExecutor()
    context = ExecutionContext(request=request, spec=spec, estimate=spec.estimate, attempt=1,
                               approved_side_effect=SideEffect.WRITE)
    try:
        raw = await (await executor.start(context)).task
    finally:
        await executor.close()
    receipt = ExecutionReceipt(
        decision_id="fixture:no-routing-decision", action_id=request.action_id,
        capability=spec.capability, executor_id=spec.id, executor_kind=spec.kind,
        status=raw.status, started_at=started, ended_at=utc_now(), estimated=spec.estimate,
        actual_resources=raw.resources, accounting=raw.accounting,
        execution_success=raw.status == ExecutionStatus.SUCCESS,
        error_type=raw.error_type,
        metadata={"evidence_kind": "synthetic", "scope": "upstream coordinator batch only",
                  "execution_evidence": raw.metadata["execution_evidence"]},
    )
    store = ReceiptStore(str(database))
    try:
        store.save_receipt(receipt)
        # Immutable snapshot also detects later receipt-store replacement.
        reference = AssessmentRepository(store).put("toolkit_fixture_receipt", receipt.receipt_id, receipt)
    finally:
        store.close()
    if raw.status != ExecutionStatus.SUCCESS:
        raise ValueError(f"Upstream coordinator {raw.status.value}; receipt retained as {reference}")
    return str(raw.output), receipt.receipt_id


def normalize(output: Path, stack: dict, environment: dict, rows: list[dict],
              suite: dict, receipt_id: str, worker_digest: str, bridge_digest: str,
              artifact_hashes: dict[str, str]) -> EvidenceBundle:
    """Normalize checked fake-harness records, never upstream usage estimates."""
    store = ReceiptStore(str(output / "receipts.sqlite3"))
    try:
        repository = AssessmentRepository(store)
        receipt = store.get_receipt(receipt_id)
        snapshot = repository.get("toolkit_fixture_receipt", receipt_id)
        if (receipt is None or content_digest(receipt) != content_digest(snapshot)
                or receipt.status != ExecutionStatus.SUCCESS
                or receipt.metadata.get("evidence_kind") != "synthetic"
                or receipt.executor_id != "toolkit.fixture.coordinator"):
            raise ValueError("Missing, changed or unsuccessful fixture coordinator receipt")
        if len(rows) != len(suite["evals"]) * 2:
            raise ValueError("Fixture bundle must contain every expected control/treatment pair")
        plan_ref = repository.put("toolkit_fixture_plan", receipt_id,
                                 FixtureRecord(facts={"stack": stack, "environment": environment,
                                                      "worker_sha256": worker_digest}))
        verification_ref = repository.put("toolkit_fixture_verification", receipt_id,
                                         FixtureRecord(facts={"runs": rows, "artifacts": artifact_hashes,
                                                              "verifier_sha256": bridge_digest}))
        cases = {case["id"]: case for case in suite["evals"]}
        expected = {(case, arm) for case in cases for arm in ("without_skill", "with_skill")}
        if {(row["case"], row["arm"]) for row in rows} != expected:
            raise ValueError("Fixture bundle has duplicated or mismatched arms")
        candidate = SourcePin(**stack["fixture_source"])
        adapter = AdapterCapabilities(adapter_id="agent-skill-eval.fake", implementation_sha256=bridge_digest,
                                      hosts=("fake",), candidate_types=("skill",), optional_invocation=True,
                                      telemetry=(), containment="unverified")
        runs = []
        for row in rows:
            case = cases[row["case"]]
            if (row["evidence_kind"] != "synthetic" or case.get("force_skill_invocation") is not False
                    or row["exposed"] is not (row["arm"] == "with_skill")
                    or type(row["verified"]) is not bool):
                raise ValueError("Only checked optional-invocation synthetic fixture records can be normalized")
            runs.append(EvaluationRun(
                run_id=f"{row['case']}.{row['arm']}", plan_ref=plan_ref,
                candidate_sha256=candidate.artifact_sha256, adapter_sha256=bridge_digest,
                host="fake", host_version=stack["evaluator"]["version"], model="fixture.none", effort="not-applicable",
                shared_environment_sha256=content_digest(environment), worker_sha256=worker_digest,
                task_sha256=content_digest(case), task_family=row["case"],
                verifier_sha256=bridge_digest, prompt_sha256=content_digest({"prompt": case["prompt"]}),
                arm="treatment" if row["arm"] == "with_skill" else "control", mode="optional",
                candidate_exposed=row["exposed"], candidate_invoked=None,
                verification="pass" if row["verified"] else "fail", verification_ref=verification_ref,
                status="completed", retries=0, evidence_kind="synthetic", receipt_refs=(content_digest(receipt),),
            ))
        bundle = EvidenceBundle(candidate=candidate, adapter=adapter, runs=tuple(runs))
        bundle_ref = repository.put("toolkit_fixture_bundle", receipt_id,
                                    FixtureRecord(facts=bundle.model_dump(mode="json")))
        comparison = ComparisonReport(evidence_bundle_ref=bundle_ref, plan_ref=plan_ref,
                                      outcome="NOT_ASSESSED", evidence_kind="synthetic", limitations=(
                                          "Engineered fake-harness outcomes do not measure candidate benefit.",
                                          "One coordinator receipt is shared by the batch; it is not per-trial model accounting.",
                                          "Separate controlled workers and live host compatibility remain unverified.",
                                      ))
        (output / "toolkit-evidence.json").write_text(bundle.model_dump_json(indent=2) + "\n")
        (output / "toolkit-comparison.json").write_text(comparison.model_dump_json(indent=2) + "\n")
        (output / "coordinator-receipt.json").write_text(receipt.model_dump_json(indent=2) + "\n")
        return bundle
    finally:
        store.close()


def verify(output: Path) -> EvidenceBundle:
    """Resolve the saved fixture bundle against its receipt and artifact records."""
    import hashlib
    import json

    bundle = EvidenceBundle.model_validate(read_json(output / "toolkit-evidence.json"))
    comparison = ComparisonReport.model_validate(read_json(output / "toolkit-comparison.json"))
    if comparison.outcome != "NOT_ASSESSED" or comparison.evidence_kind != "synthetic" or not bundle.runs:
        raise ValueError("Fixture report must remain synthetic and unassessed")
    import sqlite3
    from urllib.parse import quote

    database = output / "receipts.sqlite3"
    if database.is_symlink() or not database.is_file():
        raise ValueError("Fixture receipt store is missing or linked")
    wal = database.with_name(database.name + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError("Close the fixture writer before verifying its receipt snapshot")
    connection = sqlite3.connect("file:" + quote(str(database.resolve()), safe="/") + "?mode=ro&immutable=1", uri=True)

    def record(kind: str, reference: str) -> dict:
        row = connection.execute(
            "SELECT payload_json FROM assessment_records WHERE kind=? AND (id=? OR digest=?)",
            (kind, reference, reference),
        ).fetchone()
        if row is None:
            raise ValueError("Fixture evidence record is missing")
        return json.loads(row[0])

    try:
        stored = record("toolkit_fixture_bundle", comparison.evidence_bundle_ref)
        if stored != {"facts": bundle.model_dump(mode="json")} or content_digest(stored) != comparison.evidence_bundle_ref:
            raise ValueError("Fixture bundle changed after verification")
        exported = ExecutionReceipt.model_validate(read_json(output / "coordinator-receipt.json"))
        row = connection.execute("SELECT payload_json FROM receipts WHERE receipt_id=?", (exported.receipt_id,)).fetchone()
        receipt = ExecutionReceipt.model_validate_json(row[0]) if row else None
        snapshot = record("toolkit_fixture_receipt", exported.receipt_id)
        if receipt is None or content_digest(receipt) != content_digest(snapshot) or receipt != exported:
            raise ValueError("Coordinator receipt changed or is missing")
        for run in bundle.runs:
            if (run.plan_ref != comparison.plan_ref or run.evidence_kind != "synthetic"
                    or run.receipt_refs != (content_digest(receipt),)):
                raise ValueError("Fixture evidence binding is inconsistent")
            plan = record("toolkit_fixture_plan", run.plan_ref)
            verification = record("toolkit_fixture_verification", run.verification_ref)
            if content_digest(plan) != run.plan_ref or content_digest(verification) != run.verification_ref:
                raise ValueError("Fixture definition changed after verification")
            for name, expected in verification["facts"]["artifacts"].items():
                path = output / name
                if (Path(name).is_absolute() or ".." in Path(name).parts
                        or path.is_symlink() or not path.resolve().is_relative_to(output.resolve())
                        or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                    raise ValueError("Upstream artifact changed after verification")
        if comparison.analysis_ref is not None:
            raise ValueError("Synthetic fixture has no live analysis")
        return bundle
    finally:
        connection.close()
