"""Proposed installed-wheel checks; do not execute before exact approval."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

from aeep.assessment import verification
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, SideEffect
from aeep_toolkit.cli import main
from aeep_toolkit.workflow import StackConfiguration
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition, WorkflowPlanLink
from aeep_toolkit.workflow_security import (
    ScanContainerExecutor, ScannerRuntimeDefinition, WorkflowScanRecord, scan_spec,
)


def interpreter_checks(runtime: ScannerRuntimeDefinition) -> dict:
    spec = scan_spec(runtime)
    context = ExecutionContext(
        request=ActionRequest(capability=spec.capability), spec=spec,
        estimate=spec.estimate, attempt=1,
        attempt_id="inert-installed-scanner-launch-check",
        approved_side_effect=SideEffect.READ,
    )
    executor = ScanContainerExecutor(
        runtime.environment,
        runtime_digest=runtime.executable_dependencies[str(runtime.environment.container_runtime)],
    )
    argv, _name = executor.command(context)
    assert argv[argv.index("--entrypoint") + 1] == "python3"
    assert spec.config["argv"][0] == "/opt/aeep-scanner/bin/python"
    assert argv[argv.index("--network") + 1] == "none"
    assert "--pull=never" in argv and "--read-only" in argv
    assert argv[argv.index("--user") + 1] == "65534:65534"
    return {
        "protocol_interpreter": "python3",
        "scanner_child_interpreter": "/opt/aeep-scanner/bin/python",
        "launch_generated_only": True, "container_started": False,
    }


def run(request: dict) -> dict:
    root = Path(verification.__file__).resolve().parents[3]
    assert verification.verification_source_digest(root) == request["installed_source"]
    assert "scanner" in StackConfiguration.model_fields
    assert "execution_evidence_ref" in WorkflowScanRecord.model_fields
    assert "executable_dependencies" in ScannerRuntimeDefinition.model_fields
    assert "component_refs" not in WorkflowPlanLink(
        operation_id="fixture", assessment_plan_id="fixture", assessment_plan_digest="a" * 64,
    ).model_dump()
    assert WorkflowAccountingDefinition.model_json_schema()["properties"]["schema_version"]["enum"] == [
        "aeep.toolkit.workflow-accounting.v1", "aeep.toolkit.workflow-accounting.v2",
        "aeep.toolkit.workflow-accounting.v3",
    ]
    launch = interpreter_checks(ScannerRuntimeDefinition.model_validate(request["scanner_runtime"]))
    checks = []
    for argv, required in [
        (["candidate", "--help"], "--stage"),
        (["install-plan", "--help"], "--storage-exception"),
        (["workflow", "scan", "--help"], "--reviewed-digest"),
        (["workflow", "define-scanner", "--help"], "--manifest"),
        (["workflow", "run", "--help"], "--scan-report"),
        (["workflow", "report", "--help"], "--scan-report"),
    ]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                main(argv)
            except SystemExit as error:
                assert error.code == 0
            else:
                raise AssertionError("expected help exit")
        assert required in output.getvalue()
        checks.append(" ".join(argv[:-1]))
    return {
        "passed": True, "installed_source": request["installed_source"],
        "cli_help_checks": checks, "interpreter_checks": launch,
        "models": 0, "upstream_scanner_executed": False, "task_execution": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
