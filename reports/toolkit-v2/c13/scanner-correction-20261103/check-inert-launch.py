"""Check source command generation only; no installed/runtime evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location("proposed_package_check", HERE / "package-check.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
runtime = module.ScannerRuntimeDefinition.model_validate_json(
    (HERE.parent / "workflow-scanner-20261102/scanner-runtime.json").read_bytes(),
)
facts = module.interpreter_checks(runtime)
command = module.ScanContainerExecutor.command


def old_invalid_launch(self, context):
    argv, name = command(self, context)
    argv[argv.index("--entrypoint") + 1] = "/opt/aeep-scanner/bin/python"
    return argv, name


with patch.object(module.ScanContainerExecutor, "command", old_invalid_launch):
    try:
        module.interpreter_checks(runtime)
    except AssertionError:
        pass
    else:
        raise AssertionError("The installed check would accept the old carrier defect")

print(json.dumps({
    "passed": True, "evidence_kind": "first_party_source_command_generation",
    "corrected_source_launch": facts, "old_private_protocol_launch_rejected": True,
    "container_execution": False, "installed_wheel_checked": False,
    "upstream_execution": False, "full_source_verification": False,
}))
