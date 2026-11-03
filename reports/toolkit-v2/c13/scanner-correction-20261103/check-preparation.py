"""Small in-memory first-party checks; never execute a runtime or boundary."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("proposed_bootstrap", HERE / "bootstrap-probe.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
path = Path("/reviewed/src/aeep/assessment/container_worker.py")
data = b"first-party in-memory protocol substitute"
identity = hashlib.sha256(data).hexdigest()
checks = []

with patch.object(Path, "is_symlink", return_value=False), \
        patch.object(Path, "resolve", lambda self: self), \
        patch.object(Path, "read_bytes", return_value=data), \
        patch.object(module.importlib, "import_module") as importer:
    importer.return_value = SimpleNamespace(__file__=str(path))
    assert module.protocol_check(str(path), identity)["passed"] is True
    checks.append("verified protocol path and bytes permit the reviewed import")
    importer.reset_mock()
    assert module.protocol_check(str(path), "f" * 64)["category"] == "PROTOCOL_SOURCE_DRIFT"
    importer.assert_not_called()
    checks.append("source drift blocks import")
    assert module.protocol_check("/unreviewed/file.py", identity)["category"] == "INVALID_REVIEWED_INPUT"
    importer.assert_not_called()
    checks.append("wrong protocol path blocks import")
    importer.side_effect = ModuleNotFoundError("unretained exception secret", name="psutil")
    result = module.protocol_check(str(path), identity)
    assert result == {"passed": False, "category": "MISSING_RUNTIME_DEPENDENCY", "missing_module": "psutil"}
    assert "secret" not in json.dumps(result)
    checks.append("missing known dependency is retained without exception text")
    importer.side_effect = ModuleNotFoundError("unretained", name="private_unreviewed_module")
    assert module.protocol_check(str(path), identity)["missing_module"] == "other"
    checks.append("unknown missing module name is minimized")
    importer.side_effect = RuntimeError("unretained exception secret")
    result = module.protocol_check(str(path), identity)
    assert result == {"passed": False, "category": "PROTOCOL_IMPORT_FAILED"}
    checks.append("other import failure fails closed without exception text")
    importer.side_effect = None
    importer.return_value = SimpleNamespace(__file__="/another/container_worker.py")
    assert module.protocol_check(str(path), identity)["category"] == "PROTOCOL_IMPORT_PATH_MISMATCH"
    checks.append("imported module from another location is rejected")

print(json.dumps({
    "passed": True, "checks": checks,
    "evidence_kind": "first_party_in_memory_substitutes",
    "container_execution": False, "actual_protocol_import": False,
    "upstream_execution": False, "full_source_verification": False,
}))
