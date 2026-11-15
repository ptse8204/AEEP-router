"""First-party fixtures exercise revalidation of an existing scheduler boundary."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep.assessment.models import ConformanceProbeRequest
from aeep.errors import ConfigurationError
from aeep.execution import EventJournal
from aeep.models import ExecutorSpec, RawExecution, ResourceVector
from aeep_toolkit import ase_boundary_evidence as boundary
from aeep_toolkit.workflow_evidence import OperationLink


@pytest.fixture
def retained(tmp_path, monkeypatch):
    def bind(name, text):
        file = tmp_path / name
        file.write_text(text)
        return {"path": str(file), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}

    digest = "a" * 64
    old, new = "b" * 64, "c" * 64
    scheduler_ref = "d" * 64
    entry = {
        key: bind(key, f"fixture bytes for {key}")
        for key in ("historical_git", "current_profile", "probe", "git", "outside_canary")
    }
    operation = "fixture-native-boundary"
    argv = [
        boundary.SANDBOX,
        "-f",
        entry["current_profile"]["path"],
        str(tmp_path / "bin/python"),
        "-I",
        "-B",
        entry["probe"]["path"],
    ]
    scheduler = SimpleNamespace(
        runtime_tree_digest=digest,
        runtime_root=str(tmp_path),
        adapter_id="agent-skill-eval.controlled.v1",
        executable_dependencies={
            boundary.SANDBOX: old,
            entry["historical_git"]["path"]: entry["historical_git"]["sha256"],
        },
    )
    config = {
        "argv": argv,
        "argv_literal": True,
        "inherit_env": False,
        "env": {},
        "cwd": str(tmp_path / "work"),
        "stdin_json": True,
        "max_stdin_bytes": 16384,
        "max_output_bytes": 8192,
        "timeout_seconds": 25,
        "output": {"type": "json"},
    }
    spec = ExecutorSpec(
        id="toolkit.ase-native-compatibility",
        capability="toolkit.upstream-engineering@1",
        kind="command",
        description="First-party fixture",
        side_effect="write",
        config=config,
    )
    request = ConformanceProbeRequest(
        subject_digest=digest,
        recipe_digest=digest,
        mapping_digest=digest,
        environment_digest=digest,
        worker_digest=digest,
        authorization_id="fixture",
        definition_digests=[digest],
        executable_dependencies={},
    )
    entry.update(
        historical_definition_ref=scheduler_ref,
        operation_id=operation,
        runtime_tree_sha256=digest,
        executable_change={boundary.SANDBOX: {"original": old, "current": new}},
        stdin={"git": entry["git"]["path"], "outside": entry["outside_canary"]["path"]},
        command=argv,
        workspace=config["cwd"],
        environment={},
        request=request.model_dump(mode="json"),
    )
    payload = {
        "schema_version": "aeep.operator.toolkit-ase-native-repeat.v1",
        "agent_skill_eval": entry,
        "model_turns": 0,
        "maximum_cash_usd": 0,
        "maximum_additional_operations": 1,
        "maximum_reserved_seconds": 35,
    }
    review = bind("review.json", json.dumps(payload))
    evidence = boundary.SchedulerBoundaryEvidence(
        review=review,
        definition_ref=digest,
        receipt=OperationLink(operation_id=operation, receipt_ref=digest),
    )
    journal = EventJournal(operation)
    journal.append("execution.started", "start")
    journal.append("execution.completed", "terminal")
    observed = journal.evidence("CommandExecutor", RawExecution(status="success"))
    receipt = SimpleNamespace(
        executor_id=spec.id,
        executor_kind=spec.kind,
        actual_resources=ResourceVector(),
        metadata={
            "review_sha256": review["sha256"],
            "exit_code": 0,
            "model_turns": 0,
            "observed_checks": dict.fromkeys(boundary.REQUIRED_OBSERVATIONS, True),
            "execution_evidence": observed.model_dump(mode="json"),
            "execution_evidence_digest": observed.digest(),
        },
    )
    charge = SimpleNamespace(
        stage="ase_current_native_boundary",
        plan_id=request.plan_id,
        reserved=SimpleNamespace(
            max_operations=1, max_model_turns=0, max_cash_usd=0, max_elapsed_seconds=35
        ),
        resources=receipt.actual_resources,
    )

    def resolve(_repo, kind, ref, _model, *, reviewed):
        assert reviewed
        if kind == "scheduler":
            assert ref == scheduler_ref
            return scheduler
        assert kind == "toolkit_ase_native_compatibility" and ref == digest
        return spec

    checked = []
    monkeypatch.setattr(boundary, "_resolve", resolve)
    monkeypatch.setattr(boundary, "_receipt", lambda *_: (receipt, charge))
    monkeypatch.setattr(boundary, "verify_dependencies", checked.append)
    monkeypatch.setattr(boundary, "snapshot", lambda _: digest)

    def record(kind, identity):
        if kind == "conformance_request":
            return request.model_dump(mode="json")
        assert kind == "execution_event"
        return observed.events[int(identity.split(":")[-1])].model_dump(mode="json")

    repo = SimpleNamespace(get=record)
    return repo, scheduler_ref, scheduler, evidence, checked, new, receipt, charge


def test_exact_boundary_reuses_historical_scheduler(retained):
    repo, ref, scheduler, evidence, checked, new, *_ = retained
    assert boundary.require_ase_boundary(repo, ref, evidence) is scheduler
    assert checked == [scheduler.executable_dependencies | {boundary.SANDBOX: new}]
    assert scheduler.executable_dependencies[boundary.SANDBOX] != new


@pytest.mark.parametrize("fault", ["runtime", "artifact", "result", "journal", "budget"])
def test_unverified_native_boundary_fails_closed(retained, monkeypatch, fault):
    repo, ref, _, evidence, _, _, receipt, charge = retained
    if fault == "runtime":
        monkeypatch.setattr(boundary, "snapshot", lambda _: "f" * 64)
    elif fault == "artifact":
        entry = json.loads(Path(evidence.review.path).read_bytes())["agent_skill_eval"]

        Path(entry["git"]["path"]).write_text("changed bound artifact")
    elif fault == "result":
        receipt.metadata["observed_checks"]["network_denied"] = False
    elif fault == "journal":
        receipt.metadata["execution_evidence_digest"] = "f" * 64
    else:
        charge.reserved.max_model_turns = 1
    with pytest.raises((ConfigurationError, ValueError)):
        boundary.require_ase_boundary(repo, ref, evidence)
