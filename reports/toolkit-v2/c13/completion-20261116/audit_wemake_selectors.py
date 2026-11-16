"""Expand published prefix selectors using inert copies of literal parametrizations."""

import ast
import json
import subprocess
import sys
import tarfile
import tempfile
from importlib.metadata import version
from pathlib import Path

from check_linux_install import HERE, ROOT, WORK, get, put

from aeep_toolkit.install_runtime import file_digest

CASE = "wemake-services__wemake-python-styleguide-3382"
STAGED = WORK / "multifile-acquisition-static-handoff"
TRANSPORT = STAGED / "worker-transport"
OUT = WORK / "wemake-native-selector-preflight"
REPORT = HERE / "wemake-native-selector-preflight.json"


def fixture_source(raw):
    nodes = ast.parse(raw)
    values = {
        node.targets[0].id: node.value.value
        for node in nodes.body
        if isinstance(node, ast.Assign) and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    declared = ["import pytest"]
    for node in nodes.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        parameters = []
        for decorator in node.decorator_list:
            if (
                not isinstance(decorator, ast.Call) or ast.unparse(decorator.func) != "pytest.mark.parametrize"
                or len(decorator.args) != 2 or decorator.keywords
                or not isinstance(decorator.args[1], ast.List)
            ):
                raise ValueError("upstream parametrization stopped being a literal string list")
            name = ast.literal_eval(decorator.args[0])
            if not isinstance(name, str) or not name.isidentifier():
                raise ValueError("unexpected upstream parameter name")
            items = [
                values[item.id] if isinstance(item, ast.Name) else ast.literal_eval(item)
                for item in decorator.args[1].elts
            ]
            if not all(isinstance(item, str) for item in items):
                raise ValueError("unexpected upstream parameter type")
            parameters.append(name)
            declared.append(f"@pytest.mark.parametrize({name!r}, {items!r})")
        if not parameters or len(set(parameters)) != len(parameters):
            raise ValueError("upstream test changed its reviewed parameter structure")
        declared.append(f"def {node.name}({', '.join(parameters)}):\n    pass\n")
    return "\n".join(declared)


def expand(required, collected):
    output = {}
    for selector in required:
        matches = (
            [item for item in collected if item.startswith(selector)]
            if selector.count("[") == 1 and "]" not in selector
            else [item for item in collected if item == selector]
        )
        if not matches:
            raise ValueError("published selector matched no synthetic identity")
        output[selector] = matches
    flattened = [item for matches in output.values() for item in matches]
    if len(flattened) != len(set(flattened)):
        raise ValueError("multiple published entries map to the same identity")
    return output


def prepare():
    acquisition = get(HERE / "multifile-acquisition-result.json")
    index = TRANSPORT / "private-index.json"
    if file_digest(index) != acquisition["private_evidence_sha256"][str(index.relative_to(ROOT))]:
        raise ValueError("transport case index changed")
    (row,) = [item for item in get(index) if item["input"]["task_id"] == CASE]
    root = TRANSPORT / "protected" / CASE
    overlay = root / "tests.tar.gz"
    identities = root / "required.json"
    if file_digest(overlay) != row["protected_tests"]["sha256"] or file_digest(identities) != row["required_identities"]["sha256"]:
        raise ValueError("protected overlay or published selectors changed")
    selectors = get(identities)
    both = selectors["fail_to_pass"] + selectors["pass_to_pass"]
    (relative,) = {item.split("::", 1)[0] for item in both}
    with tarfile.open(overlay, "r:gz") as archive, archive.extractfile(relative) as stream:
        probe = fixture_source(stream.read())
    with tempfile.TemporaryDirectory(dir=WORK, prefix="wemake-literal-collection-") as temp:
        fixture = Path(temp) / Path(relative).name
        fixture.write_text(probe)
        result = subprocess.check_output([
            sys.executable, "-B", "-m", "pytest", "-q", "--collect-only", "-c", "/dev/null",
            "-p", "no:cacheprovider", "--noconftest", "--rootdir", temp, fixture.name,
        ], cwd=temp, env={"PATH": "/usr/bin:/bin", "PYTHONUTF8": "1",
                         "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}, timeout=30).decode()
    prefix = fixture.name + "::"
    collected = [relative + line.removeprefix(fixture.name) for line in result.splitlines() if line.startswith(prefix)]
    mapping = expand(both, collected)
    ready = {kind: sorted({item for selector in selectors[kind] for item in mapping[selector]})
             for kind in ("fail_to_pass", "pass_to_pass")}
    if len(collected) != len(set(collected)) or set(collected) != set(ready["fail_to_pass"]) | set(ready["pass_to_pass"]):
        raise ValueError("synthetic collection differs from the reviewed full parametrization")
    OUT.mkdir(mode=0o700)
    put(OUT / "selector-map.json", mapping)
    put(OUT / "projected-identities.json", ready)
    record = {
        "case_id": CASE, "published_revision": row["source_revision"], "pytest_version": version("pytest"),
        "published_selectors": {kind: len(items) for kind, items in selectors.items()},
        "truncated_selectors": sum("[" in item and "]" not in item for item in both),
        "synthetic_collected_identities": len(collected),
        "projected_required_identities": {kind: len(items) for kind, items in ready.items()},
        "protected_overlay_sha256": file_digest(overlay),
        "published_selectors_sha256": file_digest(identities),
        "selector_map_sha256": file_digest(OUT / "selector-map.json"),
        "projected_identities_sha256": file_digest(OUT / "projected-identities.json"),
        "upstream_code_executed": False, "real_collection_pending": True, "formal_case_adopted": False,
    }
    put(REPORT, record)
    print(json.dumps(record))


if __name__ == "__main__":
    prepare()
