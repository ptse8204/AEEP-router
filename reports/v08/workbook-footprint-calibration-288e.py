"""Bounded, synthetic workbook footprint comparison; no model or release verdict."""

import asyncio
import base64
import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "integrations/assessment-runtime"
PYTHON = Path("/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")
CODEX = Path("/Users/edwintse/.local/bin/codex").resolve()
SOURCE_DIGEST = "288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782"


def cases():
    small = json.loads((ASSETS / "workbook-grader-fixtures.json").read_text())[0]
    generated = subprocess.run([str(PYTHON), "-I", str(ASSETS / "workbook_program.py"), "generate"],
        input=json.dumps({"seed": 29, "stages": [{"split": "demo", "count": 11}]}),
        text=True, capture_output=True, check=True, timeout=15)
    large = json.loads(generated.stdout)["cases"][10]
    return {"small": {"input": small["input"], "expected": small["expected"]},
            "larger": {"input": large["input"], "expected": large["output"]}}


async def child(payload):
    from aeep.assessment.workbook import workbook_recipe
    from aeep.assessment.workbook_native import implementation_digest, validate
    from aeep.hosts.codex_sandbox import NativeSandboxConfig
    from aeep.validators import ValidationContext

    arm, case = payload["arm"], payload["case"]
    root = Path(payload["root"])
    scratch = root / "scratch"
    scratch.mkdir()
    prefix = subprocess.run([str(PYTHON), "-I", "-c", "import sys; print(sys.prefix)"],
        capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    binary_digest = "sha256:" + hashlib.sha256(CODEX.read_bytes()).hexdigest()
    boundary = NativeSandboxConfig(binary=str(CODEX), binary_sha256=binary_digest,
        project_root=str(root), read_roots=[str(Path(prefix).resolve())], write_roots=[str(scratch)])
    source = (ASSETS / "workbook_program.py").read_text()
    program = "import json,sys; ns={'__name__':'reference'}; exec(" + repr(source) + ", ns); inp=json.load(sys.stdin); print(json.dumps(ns['reference'](inp)))"
    command = [str(PYTHON), "-I", "-c", program]
    grader = runpy.run_path(str(ASSETS / "workbook_grader.py"))["grade"]
    input_value, expected = case["input"], case["expected"]
    input_bytes = len(json.dumps(input_value, separators=(",", ":")).encode())
    input_xlsx_bytes = len(base64.b64decode(input_value["workbook_b64"], validate=True))
    started = time.perf_counter()
    if arm == "native":
        env = {**os.environ, "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)}
        process = await asyncio.create_subprocess_exec(*boundary.argv(command), cwd=str(root), env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(input_value).encode()), 30)
        if process.returncode or stderr:
            raise RuntimeError("native command failed: " + str(process.returncode))
        output = json.loads(stdout)
        dispatch_ms = (time.perf_counter() - started) * 1000
        activation_ms = None
        schema_bytes = instructions_bytes = host_config_bytes = evidence_bytes = 0
        lifecycle_ms = None
        receipt_check = None
        user_summary = None
        recovery_state = None
    else:
        from aeep.assessment.repository import AssessmentRepository
        from aeep.economic.prepared import executor_fingerprint
        from aeep.mcp.server import AEEPToolService
        from aeep.models import Manifest, SideEffect, TaskScope, ValidationKind, ValidationSpec, utc_now
        from aeep.router import Router
        from aeep.tasks import activate, change_state, inspect

        recipe = workbook_recipe()
        assert recipe.extension
        spec = recipe.extension.reference.model_copy(deep=True)
        spec.id = "native.workbook.reference"
        spec.input_schema, spec.output_schema = recipe.input_schema, recipe.output_schema
        spec.config = {**spec.config, "argv": command, "native_sandbox": boundary.model_dump(mode="json"),
                       "env": {"TMPDIR": str(scratch)}, "max_output_bytes": 200000}
        spec.validators = [ValidationSpec(kind=ValidationKind.CALLBACK,
            config={"name": "aeep.workbook.native.v1", "implementation_digest": implementation_digest()})]
        manifest = root / "aeep.json"
        manifest.write_text(Manifest(database=str(root / ".aeep/state.db"), executors=[spec]).model_dump_json())
        router = Router.from_manifest(manifest)
        try:
            repo = AssessmentRepository(router.store)
            repo.review(repo.put("recipe", recipe.recipe_id, recipe))
            scope = TaskScope(scope_id="workbook-footprint", project_root=str(root),
                executor_fingerprints={spec.id: executor_fingerprint(spec)}, approval_ceiling=SideEffect.READ,
                max_attempts=1, max_attempt_seconds=30, expires_at=utc_now() + timedelta(minutes=5))
            repo.review(repo.put("task_scope", scope.scope_id, scope))
            activation = activate(router, scope.scope_id)
            service = AEEPToolService(router, profile="task", task_activation=activation.activation_id)
            activation_ms = (time.perf_counter() - started) * 1000
            schema_bytes = len(json.dumps(service.list_tools()).encode())
            instructions_bytes = len(service.instructions.encode())
            host_config_bytes = (root / ".codex/config.toml").stat().st_size
            name = "aeep_recipe_" + hashlib.sha256(recipe.capability.encode()).hexdigest()[:12]
            dispatched = time.perf_counter()
            reply = (await service.call(name, input_value))["structuredContent"]
            dispatch_ms = (time.perf_counter() - dispatched) * 1000
            if not reply["ok"]:
                raise RuntimeError("AEEP workbook dispatch or required verification failed")
            receipt = reply["receipts"][0]
            user_summary = reply["summary"]
            recovery_state = reply["recovery_state"]
            receipt_check = receipt["task_valid"] is True and any(
                item["kind"] == "callback" and item["valid"] is True and item["trust"] == "verified"
                for item in receipt["checks"])
            output = reply["output"]
            lifecycle_started = time.perf_counter()
            change_state(router, activation.activation_id, "uninstall")
            assert inspect(router, activation.activation_id)["overlay"] == "absent"
            lifecycle_ms = (time.perf_counter() - lifecycle_started) * 1000
            evidence_bytes = sum(path.stat().st_size for path in (root / ".aeep").rglob("*") if path.is_file())
        finally:
            await router.close()
    verified_started = time.perf_counter()
    built_in = validate(ValidationContext(input_value, output)).valid is True if arm == "native" else receipt_check
    external_required_check_ms = (time.perf_counter() - verified_started) * 1000 if arm == "native" else None
    grader_started = time.perf_counter()
    independent = grader({"input": input_value, "output": output, "expected": expected}) is True
    independent_ms = (time.perf_counter() - grader_started) * 1000
    if not built_in or not independent or (arm == "aeep" and not receipt_check):
        raise RuntimeError("workbook validation failed")
    output_bytes = len(json.dumps(output, separators=(",", ":")).encode())
    print(json.dumps({"arm": arm, "case": payload["case_name"], "input_json_bytes": input_bytes,
        "input_xlsx_bytes": input_xlsx_bytes, "output_json_bytes": output_bytes,
        "output_xlsx_bytes": len(base64.b64decode(output["workbook_b64"], validate=True)),
        "activation_ms": activation_ms, "dispatch_ms": dispatch_ms,
        "post_dispatch_required_check_ms": external_required_check_ms,
        "post_dispatch_independent_grader_ms": independent_ms,
        "required_validator_valid": built_in, "recipe_grader_valid": independent,
        "aeep_receipt_validator_valid": receipt_check, "schema_bytes": schema_bytes,
        "receipt_derived_summary": user_summary, "recovery_state": recovery_state,
        "instructions_bytes": instructions_bytes, "project_host_config_bytes": host_config_bytes,
        "evidence_bytes_after_uninstall": evidence_bytes, "uninstall_ms": lifecycle_ms}))


async def main():
    from aeep.assessment.verification import verification_source_digest
    from aeep.executors.command import _monitor_process
    assert verification_source_digest(ROOT) == SOURCE_DIGEST
    fixtures = cases()
    samples = []
    for case_name in ("small", "larger"):
        for arm in ("native", "aeep"):
            with tempfile.TemporaryDirectory(prefix="aeep-workbook-footprint-") as directory:
                payload = {"arm": arm, "case_name": case_name, "case": fixtures[case_name],
                           "root": str(Path(directory).resolve())}
                started = time.perf_counter()
                process = await asyncio.create_subprocess_exec(sys.executable, __file__, "--child",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stop = asyncio.Event()
                monitor = asyncio.create_task(_monitor_process(process.pid, stop))
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(payload).encode()), 60)
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                    stop.set()
                    metrics = await monitor
                if process.returncode:
                    raise RuntimeError(f"{case_name}/{arm}: " + stderr.decode()[:1500])
                sample = json.loads(stdout)
                sample["process_wall_ms"] = (time.perf_counter() - started) * 1000
                sample["sampled_process_tree"] = asdict(metrics)
                samples.append(sample)
    assert verification_source_digest(ROOT) == SOURCE_DIGEST
    report = {"schema_version": "aeep.workbook-footprint-exploratory.v1", "source_digest": SOURCE_DIGEST,
        "purpose": "Two synthetic workbook sizes, one fresh native and AEEP sample each; no acceptance or benefit verdict",
        "comparability": "Both arms use the same native sandbox, bundled Python reference, one reserved built-in validator and one independent recipe grader. The baseline runs both checks after command execution; AEEP runs the required validator inside dispatch and the independent grader afterward. AEEP additionally performs activation, receipt checks and cleanup. Host MCP and model context are excluded.",
        "measurement_limits": ["One repetition per size; no significance or cold-cache control.",
            "10ms process sampling can miss short-lived children; RSS sums may double-count shared pages.",
            "Installed Codex/Python and host are shared; this is not incremental installation or whole-host cost.",
            "Only successful reference output and normal cleanup; failure/recovery cost remains separate."],
        "samples": samples, "model_calls": 0, "downloads": 0, "release_ready": False}
    path = ROOT / "reports/v08/workbook-footprint-exploratory-final-288e.json"
    with path.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"result": str(path), "samples": len(samples)}))


if __name__ == "__main__":
    if sys.argv[1:] == ["--child"]:
        asyncio.run(child(json.load(sys.stdin)))
    else:
        asyncio.run(main())
