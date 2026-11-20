"""Appended only to the reviewed C13 observer, after its NativeCapture class."""

import re
from pathlib import Path


def diagnostic_capture(base):
    class DiagnosticCapture(base):
        def __init__(self, collect_only=False):
            super().__init__(collect_only)
            self.failure_sites = []

        def pytest_exception_interact(self, node, call, report):
            if (
                report.when not in ("setup", "call", "teardown")
                or report.outcome != "failed"
                or call.excinfo is None
                or not self._identity(node.nodeid)
                or len(self.failure_sites) >= 64
            ):
                return
            category = call.excinfo.type.__name__
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", category, flags=re.ASCII):
                category = "UnknownException"
            root = Path.cwd().resolve()
            site = {"test": node.nodeid, "phase": report.when, "category": category, "file": None, "line": None}
            for frame in reversed(call.excinfo.traceback):
                path = Path(frame.path).resolve()
                if path.is_relative_to(root):
                    name = path.relative_to(root).as_posix()
                    if len(name) <= 300 and re.fullmatch(r"[A-Za-z0-9_./-]+\.py", name):
                        site.update(file=name, line=frame.lineno + 1)
                        break
            self.failure_sites.append(site)

        def export(self):
            return super().export() | {"failure_sites": self.failure_sites}

    return DiagnosticCapture
