"""Bounded pytest diagnostics for the protected EOS reproducer."""

import re
from pathlib import Path

REPOSITORY = Path("/tmp/aeep-repository-native-v6")


def identifier(value):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.]{0,159}", value, flags=re.ASCII):
        return value
    return None


def eos_details(base, selected, overlay):
    class EOSDetails(base):
        def __init__(self, collect_only=False):
            super().__init__(collect_only)
            self.failures = []
            self.inventory = []

        def pytest_itemcollected(self, item):
            if self._identity(item.nodeid) and len(self.inventory) < 10000:
                self.inventory.append(item.nodeid)

        def pytest_collection_modifyitems(self, config, items):
            if selected:
                kept = [item for item in items if item.nodeid in selected]
                config.hook.pytest_deselected(items=[item for item in items if item.nodeid not in selected])
                items[:] = kept

        def pytest_exception_interact(self, node, call, report):
            excinfo = call.excinfo
            if (excinfo is None or not self._identity(node.nodeid) or len(self.failures) >= 64
                    or report.when not in ("setup", "call", "teardown") or report.outcome != "failed"):
                return
            error = excinfo.value
            detail = {"test": node.nodeid, "phase": report.when, "category": identifier(excinfo.type.__name__),
                      "file": None, "line": None, "attribute": None, "object_type": None, "missing_module": None}
            if isinstance(error, AttributeError):
                detail.update(attribute=identifier(error.name), object_type=identifier(type(error.obj).__name__))
            if isinstance(error, ModuleNotFoundError):
                detail["missing_module"] = identifier(error.name)
            for frame in reversed(excinfo.traceback):
                path = Path(frame.path).resolve()
                if path.is_relative_to(REPOSITORY):
                    name = path.relative_to(REPOSITORY).as_posix()
                    if len(name) <= 250 and re.fullmatch(r"[A-Za-z0-9_./-]+\.py", name, flags=re.ASCII):
                        detail.update(file=name, line=frame.lineno + 1)
                        break
            self.failures.append(detail)

        def export(self):
            return super().export() | {
                "native_ids": self.inventory,
                "failure_sites": self.failures,
                "fixture_requests": overlay(),
            }

    return EOSDetails
