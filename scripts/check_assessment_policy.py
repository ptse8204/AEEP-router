#!/usr/bin/env python3
"""Check repository policy links, core import boundaries and assessment test layers."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = {"assessment_contract", "assessment_lifecycle", "assessment_boundary",
          "codex_conformance", "live_acceptance"}


def violations(root: Path = ROOT) -> list[str]:
    errors = []
    for name in ("AGENTS.md", "README.md", "CONTRIBUTING.md", "docs/ASSESSMENT.md",
                 "integrations/aeep/skills/assess-plugin/SKILL.md"):
        if "ASSESSMENT_TESTING.md" not in (root / name).read_text(encoding="utf-8"):
            errors.append(f"{name}: missing canonical testing policy link")
    for name in ("src/aeep/router.py", "src/aeep/execution.py", "src/aeep/assessment/service.py"):
        for node in ast.walk(ast.parse((root / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and ((node.module and any(part.startswith("codex") for part in node.module.split("."))) or any("Codex" in item.name for item in node.names)):
                errors.append(f"{name}:{node.lineno}: provider implementation imported by core")
    for path in sorted((root / "tests").glob("test_v08*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        if not found & LAYERS:
            errors.append(f"{path.name}: missing assessment test layer")
    return errors


if __name__ == "__main__":
    problems = violations()
    for problem in problems:
        print(problem)
    raise SystemExit(bool(problems))
