"""First-party boundary fixtures; no real ASE import, model or container run."""

import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import manifest_with, python_spec
from test_toolkit_workflow_preparation import configured
from test_v08_campaign_foundations import suite_for

from aeep.assessment.models import AssessmentPlan, AssessmentSetupRequest, content_digest
from aeep.assessment.scheduling import SKILLRANK_DIAGNOSTIC, SchedulerDefinition, require_scheduler
from aeep.benchmarking import BenchmarkRoute, BenchmarkRunner, BenchmarkTrial
from aeep.errors import ConfigurationError
from aeep.models import ExecutorSpec, RawExecution
from aeep.router import Router
from aeep_toolkit import ase_scheduler
from aeep_toolkit.ase_scheduler import ASE_ARTIFACT, ASE_REVISION, AgentSkillEvalCoordinator
from aeep_toolkit.install_runtime import snapshot
from aeep_toolkit.installation import manifest_digest
from aeep_toolkit.models import ExtensionManifest
from aeep_toolkit.skillrank_scheduler import (
    BINARY_NAME,
    CASE_SLOT,
    REVISION,
    SANDBOX,
    SkillRankCoordinator,
    boundary_profile,
)
from aeep_toolkit.workflow import prepare_stack
from aeep_toolkit.workflow_preparation import prepare_canonical


def scheduler_definition(tmp_path):
    profile = tmp_path / "scheduler.sb"
    profile.write_text("(version 1)\n(deny default)\n")
    return SchedulerDefinition(
        adapter_id="agent-skill-eval.controlled.v1",
        source_revision=ASE_REVISION,
        artifact_sha256=ASE_ARTIFACT,
        executable_dependencies={str(profile): hashlib.sha256(profile.read_bytes()).hexdigest()},
        workspace=str(tmp_path / "owned-scheduler"),
        runtime_root=str(tmp_path / "runtime"),
        runtime_tree_digest="a" * 64,
        boundary_profile=str(profile),
        overhead_seconds=30,
        maximum_requests=6,
        executor=ExecutorSpec(
            id="ase.scheduler",
            capability="assessment.scheduler@1",
            kind="command",
            description="First-party fixture only; never executed as upstream evidence",
            side_effect="write",
            config={
                "argv": [
                    "/usr/bin/sandbox-exec",
                    "-f",
                    str(profile),
                    str(tmp_path / "runtime/bin/python"),
                    "-I",
                    "-B",
                    "-m",
                    "aeep_toolkit.ase_child",
                ],
                "argv_literal": True,
                "inherit_env": False,
                "stdin_json": True,
                "cwd": str(tmp_path / "owned-scheduler"),
                "env": {
                    "HOME": str(tmp_path / "owned-scheduler/home"),
                    "TMPDIR": str(tmp_path / "owned-scheduler/tmp"),
                },
                "timeout_seconds": 30,
                "max_output_bytes": 65536,
                "output": {"type": "jsonl", "match": {"kind": "done"}},
            },
        ),
    )


def external_plan(tmp_path, monkeypatch, *, engine="agent-skill-eval", native_binary=None):
    path, service, _cases, _rights = configured(tmp_path, grader_container=engine == "skillrank")
    definition = scheduler_definition(tmp_path)
    if engine == "skillrank":
        runtime = tmp_path / "runtime"
        binary = runtime / "bin" / BINARY_NAME
        binary.parent.mkdir(parents=True)
        if native_binary is None:
            binary.write_text("first-party substitute; never executed")
        else:
            shutil.copyfile(native_binary, binary)
            binary.chmod(0o555)
        binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
        profile = tmp_path / "scheduler.sb"
        profile.write_text(boundary_profile(runtime, tmp_path / "owned-scheduler"))
        executor = definition.executor.model_copy(deep=True)
        executor.config["argv"] = [SANDBOX, "-f", str(profile), str(binary)]
        definition = SchedulerDefinition.model_validate(
            definition.model_dump(mode="json") | {
                "adapter_id": SKILLRANK_DIAGNOSTIC, "source_revision": REVISION,
                "artifact_sha256": binary_sha, "maximum_requests": 2,
                "runtime_tree_digest": snapshot(runtime), "executor": executor.model_dump(mode="json"),
                "executable_dependencies": {
                    SANDBOX: hashlib.sha256(Path(SANDBOX).read_bytes()).hexdigest() if native_binary else "c" * 64,
                    str(profile): hashlib.sha256(profile.read_bytes()).hexdigest(),
                    str(binary): binary_sha,
                },
            }
        )
        # This fixture supplies no host runtime and never executes the substitute.
        if native_binary is None:
            monkeypatch.setattr("aeep.assessment.scheduling.verify_dependencies", lambda _: None)
    source = tmp_path / "agent_skill_eval/__init__.py"
    source.parent.mkdir()
    source.write_text("synthetic fixture")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    definition.executable_dependencies[str(source)] = sha
    monkeypatch.setattr(ase_scheduler, "ASE_SOURCE_FILES", {"agent_skill_eval/__init__.py": sha})
    if engine == "agent-skill-eval":
        monkeypatch.setattr(ase_scheduler, "snapshot", lambda _: "a" * 64)
    ref = service.repository.put("scheduler", content_digest(definition), definition)
    service.repository.review(ref)
    request_path = tmp_path / "request.json"
    request = AssessmentSetupRequest.model_validate_json(request_path.read_bytes())
    request = AssessmentSetupRequest.model_validate(
        request.model_dump(mode="json")
        | {"schema_version": "assessment.setup.v3", "scheduler_digest": ref}
    )
    request_path.write_text(request.model_dump_json())
    data = json.loads(path.read_text())
    selected = data["configurations"]["document-data"]
    selected["evaluator"] = engine
    selected["components"] = [engine, "skillsbench"]
    selected["preparation"]["request"]["sha256"] = hashlib.sha256(
        request_path.read_bytes()
    ).hexdigest()
    scheduler_path = tmp_path / "scheduler.json"
    scheduler_path.write_text(definition.model_dump_json())
    selected["scheduler"] = {
        "path": scheduler_path.name,
        "sha256": hashlib.sha256(scheduler_path.read_bytes()).hexdigest(),
    }
    registry_path = tmp_path / "registry.json"
    registry = json.loads(registry_path.read_text())
    entry = registry["extensions"][0]
    old_digest = manifest_digest(ExtensionManifest.model_validate(entry))
    entry["extension_id"] = engine
    registry_path.write_text(json.dumps(registry))
    new_digest = manifest_digest(ExtensionManifest.model_validate(entry))
    policy_path = tmp_path / "policy.json"
    policy = json.loads(policy_path.read_text())
    policy["reviewed_dependency_manifests"] = [
        new_digest if d == old_digest else d for d in policy["reviewed_dependency_manifests"]
    ]
    policy_path.write_text(json.dumps(policy))
    for name in ("registry", "policy"):
        data[name]["sha256"] = hashlib.sha256(
            (tmp_path / (name + ".json")).read_bytes()
        ).hexdigest()
    path.write_text(json.dumps(data))
    monkeypatch.setattr(Router, "from_manifest", lambda *_: service.router)

    async def no_close():
        pass

    monkeypatch.setattr(service.router, "close", no_close)
    preview = prepare_stack(path, "document-data")
    result = prepare_canonical(
        path,
        "document-data",
        reviewed_digest=preview["review_sha256"],
        destination=tmp_path / "prepared",
    )
    plan = AssessmentPlan.model_validate(service.repository.get("plan", result["plan_id"]))
    for digest in plan.definition_digests:
        service.repository.review(digest)
    return service, plan, definition, path


def test_external_plan_prepares_through_ordinary_workflow_and_preserves_old_versions(
    tmp_path, monkeypatch
):
    service, plan, definition, _ = external_plan(tmp_path, monkeypatch)
    assert plan.schema_version == "assessment.plan.v8"
    assert plan.scheduler_digest == content_digest(definition)
    assert plan.scheduler_digest in plan.definition_digests
    preview = prepare_stack(tmp_path / "prepared/workflow.json", "document-data")
    assert preview["scheduler"]["definition_ref"] == plan.scheduler_digest
    assert not preview["blockers"]
    assert (
        service.repository.store._connection.execute(
            "SELECT count(*) FROM assessment_jobs"
        ).fetchone()[0]
        == 0
    )
    legacy = plan.model_dump(mode="json")
    legacy["schema_version"] = "assessment.plan.v7"
    legacy.pop("scheduler_digest")
    old = AssessmentPlan.model_validate(legacy)
    assert "scheduler_digest" not in old.model_dump(mode="json")
    with pytest.raises(ValueError, match="v8"):
        AssessmentPlan.model_validate(
            plan.model_dump(mode="json") | {"schema_version": "assessment.plan.v7"}
        )


@pytest.fixture
def external(tmp_path, monkeypatch):
    value = external_plan(tmp_path, monkeypatch)
    yield value
    value[0].router.store.close()


async def test_no_implicit_managed_fallback_before_job_claim(external, monkeypatch):
    service, plan, _, _ = external
    monkeypatch.setattr(service, "_verify_dependencies", lambda *_: None)
    # Scope/job setup is synthetic; this test never starts an executor.
    with service.router.store._immediate_transaction() as connection:
        connection.execute(
            "INSERT INTO assessment_jobs(id,plan_id,state) VALUES ('fixture-job',?,'queued')",
            (plan.plan_id,),
        )
    with pytest.raises(ConfigurationError, match="scheduler differs"):
        await service.run("fixture-job")
    assert service.status("fixture-job")["state"] == "queued"


@pytest.mark.parametrize("mutation", ["revoke", "bytes", "unreviewed"])
def test_scheduler_review_and_drift_are_checked(tmp_path, monkeypatch, mutation):
    service, plan, definition, _ = external_plan(tmp_path, monkeypatch)
    if mutation == "bytes":
        (tmp_path / "scheduler.sb").write_text("changed")
    elif mutation == "revoke":
        service.repository.review(plan.scheduler_digest, revoke=True)
    else:
        with service.router.store._immediate_transaction() as connection:
            connection.execute(
                "DELETE FROM assessment_reviews WHERE digest=?", (plan.scheduler_digest,)
            )
    with pytest.raises(ConfigurationError):
        require_scheduler(service.repository, content_digest(definition))


@pytest.mark.parametrize(
    "fault", [None, "wrong-slot", "repeat", "missing", "forged-grade", "failure"]
)
async def test_bridge_preserves_trials_costs_and_rejects_protocol_faults(
    tmp_path, monkeypatch, fault, external
):
    service, plan, _definition, _ = external
    completed = []

    async def execute(slot):
        await asyncio.sleep(0.01)
        completed.append(slot)
        return BenchmarkTrial(
            trial_id="canonical-" + slot,
            run_id="run",
            suite_id=plan.plan_id,
            case_id="case",
            route_id=plan.candidate_id,
            condition="router-fresh",
            repetition=0,
            phase="qualification",
            state="complete",
            valid=True,
        )

    class ChildFixture:
        def __init__(self, stdout_observer):
            self.observe = stdout_observer

        async def start(self, context):
            async def program():
                data = context.request.input
                message = {"kind": "trial", "slot": "0", "run_token": data["run_token"]}
                if fault == "wrong-slot":
                    message["slot"] = "1"
                if fault != "missing":
                    self.observe((json.dumps(message) + "\n").encode())
                if fault == "repeat":
                    self.observe((json.dumps(message) + "\n").encode())
                if fault == "missing":
                    return RawExecution(status="success", output={})
                target = tmp_path / "owned-scheduler/responses/0.json"
                for _ in range(100):
                    if target.exists():
                        break
                    await asyncio.sleep(0.002)
                summary = {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0, "skipped": 0}
                if fault == "forged-grade":
                    summary["passed"] = 0
                return RawExecution(
                    status="failed" if fault == "failure" else "success",
                    output={
                        "kind": "done",
                        "grades": [{"slot": "0", "summary": summary}],
                        "upstream_timing_is_compatibility_only": True,
                    },
                )

            return SimpleNamespace(task=asyncio.create_task(program()))

        async def cancel(self, handle):
            handle.task.cancel()

        async def close(self):
            pass

    monkeypatch.setattr(ase_scheduler, "CommandExecutor", ChildFixture)
    coordinator = AgentSkillEvalCoordinator(service.repository, plan)
    if fault:
        with pytest.raises(ConfigurationError):
            await coordinator.coordinate(("0",), execute)
    else:
        await coordinator.coordinate(("0",), execute)
        record = service.repository.get("scheduler_observation", plan.plan_id)
        assert record["trial_refs"]["0"]
        assert record["upstream_timing_is_compatibility_only"] is True
        assert completed == ["0"]
        with pytest.raises(ConfigurationError, match="workspace exists"):
            await coordinator.coordinate(("0",), execute)
    operations = service.repository.operation_ledger(plan.plan_id).operations
    assert len(operations) == 1 and operations[0].stage == "external_scheduler"
    assert operations[0].elapsed_seconds is not None
    receipts = service.router.store.list_receipts()
    if completed:
        assert receipts and receipts[0].metadata["nested_intervals_excluded_seconds"] >= 0.01


@pytest.mark.parametrize("fault", ["omitted", "duplicate", "reordered", "swallowed", "holdout"])
async def test_scheduling_port_cannot_bypass_canonical_claims(tmp_path, fault):
    spec = python_spec("local", "aeep.examples.tools:text_stats")
    suite = suite_for(BenchmarkRoute(route_id="local", executor_id="local"))
    suite.cases[0].split = "holdout" if fault == "holdout" else "qualification"

    class Coordinator:
        definition_digest = "a" * 64

        async def coordinate(self, slots, execute):
            if fault == "omitted":
                return
            if fault == "reordered":
                await execute("1")
            if fault == "swallowed":
                with pytest.raises(ConfigurationError):
                    await execute("1")
                return
            await execute(slots[0])
            await execute(slots[0])

    runner = BenchmarkRunner(lambda: Router(manifest_with(spec)), tmp_path / "trial.sqlite3")
    try:
        with pytest.raises(ConfigurationError):
            await runner.run(suite, coordinator=Coordinator())
        if fault != "duplicate":
            assert not runner.connection.execute("SELECT * FROM trials").fetchall()
        else:
            assert runner.connection.execute("SELECT count(*) FROM trials").fetchone()[0] == 1
    finally:
        runner.connection.close()


async def test_scheduling_port_reuses_actual_first_party_execution_and_receipts(tmp_path):
    spec = python_spec("local", "aeep.examples.tools:text_stats")
    suite = suite_for(BenchmarkRoute(route_id="local", executor_id="local"))
    suite.cases[0].split = "qualification"
    observed = []

    class Coordinator:
        definition_digest = "a" * 64

        async def coordinate(self, slots, execute):
            for slot in slots:
                observed.append(await execute(slot))

    runner = BenchmarkRunner(lambda: Router(manifest_with(spec)), tmp_path / "trial.sqlite3")
    try:
        report = await runner.run(suite, coordinator=Coordinator())
        assert report.trials == observed and observed[0].valid
        assert runner.connection.execute("SELECT count(*) FROM trial_receipts").fetchone()[0] == 1
    finally:
        runner.connection.close()


def test_skillrank_plan_preserves_exact_pair_and_cannot_be_read_as_ase(tmp_path, monkeypatch):
    service, plan, definition, _ = external_plan(tmp_path, monkeypatch, engine="skillrank")
    try:
        assert plan.schema_version == "assessment.plan.v9"
        assert [route.executor_id for route in plan.suite.routes] == [plan.baseline_id, plan.candidate_id]
        coordinator = SkillRankCoordinator(service.repository, plan)
        payload = coordinator.prepare_payload(tmp_path, ("0", "1"), "a" * 64)
        assert payload["case_id"] == CASE_SLOT and payload["timeout_seconds"] == 15
        assert "task" not in payload and "files" not in payload
        with pytest.raises(ConfigurationError, match="reviewed ASE"):
            AgentSkillEvalCoordinator(service.repository, plan)
        data = plan.model_dump(mode="json")
        with pytest.raises(ValueError, match="bounded required-use"):
            AssessmentPlan.model_validate(data | {"schema_version": "assessment.plan.v8"})
        data["suite"]["routes"].reverse()
        with pytest.raises(ValueError, match="control then treatment"):
            AssessmentPlan.model_validate(data)
        unrelated = tmp_path / "runtime" / "unrelated"
        unrelated.write_text("out of scope")
        with pytest.raises(ConfigurationError, match="only the reviewed bridge"):
            coordinator.require_runtime()
        unrelated.unlink()
        profile = tmp_path / "scheduler.sb"
        profile.write_text("(allow default)")
        with pytest.raises(ConfigurationError, match="bounded SkillRank"):
            SkillRankCoordinator(service.repository, plan)
        assert definition.maximum_requests == 2
    finally:
        service.router.store.close()


@pytest.fixture
def skillrank_external(tmp_path, monkeypatch):
    value = external_plan(tmp_path, monkeypatch, engine="skillrank")
    yield value
    value[0].router.store.close()


@pytest.mark.parametrize("fault", [None, "swapped", "forged", "missing"])
async def test_skillrank_callbacks_keep_grades_and_charges_canonical(
    tmp_path, monkeypatch, skillrank_external, fault
):
    service, plan, _, _ = skillrank_external
    coordinator = SkillRankCoordinator(service.repository, plan)
    completed = []

    async def execute(slot):
        completed.append(slot)
        return BenchmarkTrial(
            trial_id=f"synthetic-{slot}", run_id="synthetic", suite_id=plan.suite.suite_id,
            case_id=plan.suite.cases[0].case_id,
            route_id=(plan.baseline_id, plan.candidate_id)[int(slot)],
            condition="fresh-worker", repetition=0, phase="qualification",
            state="complete", valid=slot == "0",
        )

    class ChildFixture:
        def __init__(self, *, stdout_observer):
            self.observe = stdout_observer

        async def start(self, context):
            async def program():
                token = context.request.input["run_token"]
                workspace = tmp_path / "owned-scheduler/responses"
                rows = []
                for arm in ("control", "treatment"):
                    sent = "treatment" if fault == "swapped" else arm
                    self.observe((json.dumps({"kind": "trial", "case_id": CASE_SLOT,
                                              "run_token": token, "arm": sent}) + "\n").encode())
                    if fault == "missing" and arm == "control":
                        return RawExecution(status="failed")
                    target = workspace / (arm + ".json")
                    for _ in range(500):
                        if target.exists():
                            break
                        await asyncio.sleep(0.002)
                    row = json.loads(target.read_text())
                    rows.append({key: row[key] for key in ("arm", "canonical_valid", "trial_ref")})
                if fault == "forged":
                    rows[0]["canonical_valid"] = False
                return RawExecution(status="success", output={
                    "kind": "done", "run_token": token, "harness": "skillrank-runner",
                    "harness_version": "0.1.0", "upstream_numeric_fields_excluded": True,
                    "trials": rows,
                })
            return SimpleNamespace(task=asyncio.create_task(program()))

        async def cancel(self, handle):
            handle.task.cancel()

        async def close(self):
            pass

    monkeypatch.setattr(ase_scheduler, "CommandExecutor", ChildFixture)
    if fault:
        with pytest.raises(ConfigurationError):
            await coordinator.coordinate(("0", "1"), execute)
    else:
        await coordinator.coordinate(("0", "1"), execute)
        record = service.repository.get("scheduler_observation", plan.plan_id)
        assert record["grade_summaries"]["0"]["passed"] == 1
        assert record["grade_summaries"]["1"]["failed"] == 1
        assert record["grading_semantics"].startswith("SkillRank")
        assert completed == ["0", "1"]
    if fault == "swapped":
        assert completed == []
    if fault == "missing":
        assert "1" not in completed
    ops = service.repository.operation_ledger(plan.plan_id).operations
    assert len(ops) == 1 and ops[0].elapsed_seconds is not None
