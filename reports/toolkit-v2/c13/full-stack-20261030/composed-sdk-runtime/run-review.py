"""Inert until exact approval; use the frozen, fully verified coordinator."""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
FROZEN = ROOT / ".aeep/stack-frozen-source-0cb8f956"
sys.path.insert(0, str(FROZEN / "src"))

from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import RuntimeInstallation, apply, digest, file_digest, snapshot


def verify():
    review = json.loads((HERE / "operation-review.json").read_text())
    for name, key in (("run-review.py", "driver_sha256"),
                      ("functional-check.py", "worker_sha256"),
                      ("langgraph-check.py", "langgraph_worker_sha256"),
                      ("reviewed-boundary.sb", "profile_sha256"),
                      ("source-snapshot.json", "source_snapshot_manifest_sha256"),
                      ("first-party-functional-program-check.json", "first_party_program_fixture_sha256"),
                      ("first-party-boundary-check.json", "first_party_boundary_sha256")):
        assert file_digest(HERE / name) == review[key]
    manifest = json.loads((HERE / "source-snapshot.json").read_text())
    assert manifest["snapshot_path"] == str(FROZEN)
    assert verification_source_digest(FROZEN) == manifest["source_digest"] == review["checkout_source"]
    for name, sha in manifest["files"].items():
        assert file_digest(FROZEN / name) == sha
    gates_path = ROOT / "reports/toolkit-v2/c13/component-adapters-20261031/verification/checks.json"
    assert file_digest(gates_path) == review["verification_checks_sha256"]
    gates = json.loads(gates_path.read_text())
    assert gates["source_before"] == gates["source_after"] == review["checkout_source"]
    assert len(gates["checks"]) == 13 and all(row["exit_code"] == 0 for row in gates["checks"])
    plan = RuntimeInstallation.model_validate_json((HERE / "installation.json").read_text())
    assert digest(plan) == review["installation_digest"]
    assert len(plan.wheels) == review["wheel_count"] == 61
    for wheel in plan.wheels:
        assert file_digest(Path(plan.wheelhouse) / wheel.filename) == wheel.sha256
    return review, plan


async def run(review, plan, identity):
    # Atomic attempt claim precedes installation, processes and owned state.
    with (HERE / "execution-started.json").open("x") as handle:
        handle.write(json.dumps({"review_sha256": identity, "started_at": utc_now().isoformat()}) + "\n")
    execution = HERE / "execution"
    execution.mkdir(mode=0o700)
    result = {"review_sha256": identity, "models": 0, "cash_usd": 0,
              "candidate_usefulness": "NOT_ASSESSED", "selection_usefulness": "NOT_ASSESSED",
              "components": {}, "all_stack_integrations_complete": False}
    clock = time.monotonic()
    store = ReceiptStore(execution / "outer-receipts.sqlite3")
    runtime = Path(plan.destination)
    original = None
    try:
        started = time.monotonic()
        installed = apply(plan, digest(plan))
        assert apply(plan, digest(plan)) == installed  # Existing installer performs no second installation.
        (execution / "installation.json").write_text(json.dumps(installed, indent=2) + "\n")
        original = snapshot(runtime)
        result["components"]["installation"] = {"passed": True, "idempotent": True,
            "wall_seconds": time.monotonic() - started, "runtime_retained": True}

        working = execution / "owned-work"
        working.mkdir(mode=0o700)
        for name in ("home", "tmp"):
            (working / name).mkdir(mode=0o700)
        worker = working / "functional-check.py"
        worker.write_bytes((HERE / "functional-check.py").read_bytes())
        assert file_digest(worker) == review["worker_sha256"]
        graph_worker = working / "langgraph-check.py"
        graph_worker.write_bytes((HERE / "langgraph-check.py").read_bytes())
        assert file_digest(graph_worker) == review["langgraph_worker_sha256"]
        profile = working / "boundary.sb"
        profile.write_bytes((HERE / "reviewed-boundary.sb").read_bytes())
        assert file_digest(profile) == review["profile_sha256"]
        prefix = ["/usr/bin/sandbox-exec", "-f", str(profile), str(runtime / "bin/python"), "-I", "-B"]
        env = {"PATH": "/usr/bin:/bin", "HOME": str(working / "home"),
               "TMPDIR": str(working / "tmp"), "PYTHONNOUSERSITE": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C"}
        outside = execution / "denied-write-canary"
        canary = HERE / "functional-check.py"
        code = ('import json,pathlib,socket,sqlite3,sys;'
                'c=sqlite3.connect(pathlib.Path.cwd()/"preflight.sqlite3");'
                'c.execute("create table probe(value integer)");c.execute("insert into probe values (1)");'
                'c.commit();assert c.execute("select value from probe").fetchone()==(1,);c.close();'
                'd={"sqlite_create_write_read":True}\n'
                'try:pathlib.Path(sys.argv[1]).read_bytes()\n'
                'except PermissionError:d["home_read_denied"]=True\n'
                'try:pathlib.Path(sys.argv[2]).write_text("owned-probe")\n'
                'except PermissionError:d["outside_write_denied"]=True\n'
                'with socket.socket() as s:\n'
                ' try:s.connect(("127.0.0.1",9))\n'
                ' except PermissionError:d["network_denied"]=True\n'
                'print(json.dumps(d))')
        preflight = subprocess.run([*prefix, "-S", "-c", code, str(canary), str(outside)],
                                   cwd=working, env=env, timeout=20, capture_output=True, check=False)
        (execution / "sandbox-preflight.json").write_text(json.dumps({
            "returncode": preflight.returncode,
            "stdout": preflight.stdout[:8192].decode(errors="replace"),
            "stderr": preflight.stderr[:8192].decode(errors="replace")}, indent=2) + "\n")
        boundary_ok = (preflight.returncode == 0 and not outside.exists() and json.loads(preflight.stdout) == {
            "sqlite_create_write_read": True, "home_read_denied": True,
            "outside_write_denied": True, "network_denied": True})
        result["components"]["sandbox"] = {"passed": boundary_ok}

        async def execute(name, argv, payload, seconds):
            spec = ExecutorSpec(id="toolkit." + name, capability="toolkit.upstream-engineering@1",
                kind="command", side_effect="write", description="Bounded offline exact SDK engineering",
                config={"argv": argv, "argv_literal": True, "inherit_env": False, "env": env,
                        "cwd": str(working), "stdin_json": payload is not None, "timeout_seconds": seconds,
                        "max_output_bytes": 1048576, "output": {"type": "json"}})
            action = ActionRequest(capability=spec.capability, input=payload or {})
            context = ExecutionContext(request=action, spec=spec, estimate=spec.estimate,
                                       attempt=1, approved_side_effect=SideEffect.WRITE)
            executor = CommandExecutor()
            began = utc_now()
            try:
                raw = await (await executor.start(context)).task
            finally:
                await executor.close()
            receipt = ExecutionReceipt(
                decision_id="reviewed-" + name, action_id=action.action_id,
                capability=spec.capability, executor_id=spec.id, executor_kind=spec.kind,
                status=raw.status, started_at=began, ended_at=utc_now(), estimated=spec.estimate,
                actual_resources=raw.resources, accounting=raw.accounting,
                execution_success=raw.status.value == "success", error_type=raw.error_type,
                metadata={"review_sha256": identity, "evidence_kind": "upstream_engineering", **raw.metadata})
            store.save_receipt(receipt)
            (execution / (name + "-receipt.json")).write_text(receipt.model_dump_json(indent=2) + "\n")
            (execution / (name + "-process.json")).write_text(json.dumps({
                "stdout": raw.stdout[:8192], "stderr": raw.stderr[:8192],
                "error_message": str(raw.error_message)[:8192] if raw.error_message else None}, indent=2) + "\n")
            if isinstance(raw.output, dict):
                (execution / (name + ".json")).write_text(json.dumps(raw.output, indent=2) + "\n")
            result["components"][name] = {"passed": receipt.execution_success,
                "receipt_id": receipt.receipt_id, "status": raw.status.value, "error_type": raw.error_type}
            return raw

        if boundary_ok:
            graph = await execute("langgraph-sdk", [*prefix, str(graph_worker)],
                {"review_sha256": identity, "installed_source": review["installed_source"],
                 "canary_path": str(canary)}, 90)
            if graph.status.value == "success":
                assert graph.output["operations"] == 6 and graph.output["models"] == 0
                assert len(graph.output["checks"]) == 4 and all(row["passed"] for row in graph.output["checks"])
            sdk = await execute("agent-framework-sdk", [*prefix, str(worker)],
                {"review_sha256": identity, "installed_source": review["installed_source"],
                 "canary_path": str(canary)}, 90)
            if sdk.status.value == "success":
                assert sdk.output["operations"] == 5 and sdk.output["models"] == 0
                assert len(sdk.output["checks"]) == 5 and all(row["passed"] for row in sdk.output["checks"])
        # Independent after successful installation; this still uses the same denied boundary.
        if boundary_ok:
            package_code = ('import json;from importlib.metadata import version;from pathlib import Path;'
                'from aeep.assessment.verification import verification_source_digest;'
                'import aeep.assessment.verification as v;'
                'from aeep_toolkit.agent_framework_workflow import PipelineDefinition;'
                'print(json.dumps({"aeep_version":version("aeep-agent-router"),'
                '"framework_version":version("agent-framework-core"),"langgraph_version":version("langgraph"),'
                '"source":verification_source_digest(Path(v.__file__).resolve().parents[3]),'
                '"pipeline_schema":PipelineDefinition.model_fields["schema_version"].default}))')
            package = await execute("installed-package", [*prefix, "-c", package_code], None, 30)
            if package.status.value == "success":
                assert package.output == {"aeep_version": "0.8.2", "framework_version": "1.21.0",
                    "langgraph_version": "1.2.14", "source": review["installed_source"], "pipeline_schema": "aeep.toolkit.agent-framework.v1"}
        result["runtime_unchanged"] = snapshot(runtime) == original
    except BaseException as error:
        result["error_type"] = type(error).__name__
        result["error_message"] = str(error)[:8192]
    finally:
        store.close()
        result["wall_seconds"] = time.monotonic() - clock
        result["runtime_retained"] = runtime.exists()
        result["passed"] = (not result.get("error_type") and result.get("runtime_unchanged") is True
            and set(result["components"]) == {"installation", "sandbox", "langgraph-sdk", "agent-framework-sdk", "installed-package"}
            and all(row["passed"] for row in result["components"].values()))
        (execution / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-approved")
    args = parser.parse_args()
    review, plan = verify()
    identity = file_digest(HERE / "operation-review.json")
    if args.execute_approved is None:
        print(json.dumps({"review_sha256": identity, "wheel_count": len(plan.wheels),
                          "installed": False, "executed": False}))
        return
    assert args.execute_approved == identity
    approval = json.loads((HERE / "operator-approval.json").read_text())
    assert approval["approved"] is True and approval["review_sha256"] == identity
    assert not (HERE / "execution-started.json").exists() and not (HERE / "execution").exists()
    assert not (HERE / "withdrawn.json").exists()
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + review["disk_reservation_bytes"]
    asyncio.run(run(review, plan, identity))


if __name__ == "__main__":
    main()
