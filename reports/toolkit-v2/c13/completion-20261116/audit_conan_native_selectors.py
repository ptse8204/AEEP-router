"""Bind the full Conan parameter coverage with static reads and a substituted grader."""

import argparse
import ast
import asyncio
import json
from pathlib import Path
from zipfile import ZipFile

from audit_staged_repository_graders import bind, wheel_probe_assets
from stage_repository_transport import WORK, digest, read

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import SuiteTruthV6, archive_files, grade_suite_output

CASE = "conan-io__conan-19735_interface-aeep-contract-audit"
REVISION = "4a65d65f53d2ab37f4ce0e52dc3f25cd832b2934"
INDEX = "36667d01dde573c5754894f99b13d061500eead71d0816cfc00970a5faf3fe86"
ROW = "d8c4691ef9853abc9198f375a0a6b546940d006a290111f2909d38eaaea08c8a"
TEST = "test/unittests/util/detect_test.py"
MODULES = ("test_detect_cc_versioning", "test_detect_compiler")
COMPILERS = {"detect_emcc_compiler", "detect_suncc_compiler", "detect_intel_compiler"}


def text_literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return text_literal(node.left) + text_literal(node.right)
    raise ValueError("only the pinned string literals are supported")


def version_tuple(node):
    if not isinstance(node, ast.Tuple) or len(node.elts) != 3:
        raise ValueError("expected compiler result tuple")
    name, call, executable = node.elts
    if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
            or call.func.id != "Version" or call.keywords or len(call.args) != 1):
        raise ValueError("expected pinned Version literal")
    return text_literal(name), text_literal(call.args[0]), text_literal(executable)


def declared_cases(body, name):
    tree = ast.parse(body)
    func, = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    declarations = [part for part in func.decorator_list if isinstance(part, ast.Call)
                    and ast.unparse(part.func) == "pytest.mark.parametrize"]
    decorator, = declarations
    if decorator.keywords or len(decorator.args) != 2 or not isinstance(decorator.args[1], ast.List):
        raise ValueError("custom or dynamic parameter identities need a separate review")
    fields = tuple(text_literal(decorator.args[0]).split(","))
    expected = ("version_return", "expected_version")
    if name == MODULES[1]:
        expected = ("function", *expected)
    if fields != expected:
        raise ValueError("unexpected collector parameter names")
    values = []
    for item in decorator.args[1].elts:
        if not isinstance(item, ast.List) or len(item.elts) != len(fields):
            raise ValueError("unexpected parameter row")
        if name == MODULES[0]:
            values.append(tuple(map(text_literal, item.elts)))
        else:
            compiler, line, version = item.elts
            if not isinstance(compiler, ast.Name) or compiler.id not in COMPILERS:
                raise ValueError("unknown compiler declaration")
            values.append((compiler.id, text_literal(line), version_tuple(version)))
    return values


def native_ids(body, name):
    ids = []
    for index, value in enumerate(declared_cases(body, name)):
        parts = []
        for part in value:
            if isinstance(part, str):
                if any(char != "\n" and not 32 <= ord(char) < 127 for char in part):
                    raise ValueError("unreviewed nonprintable or non-ASCII ID")
                parts.append(part.encode("unicode_escape").decode("ascii"))
            else:
                parts.append(f"expected_version{index}")
        joined = "-".join(parts)
        ids.append(f"{TEST}::{name}[{joined}]")
    if len(set(ids)) != len(ids):
        raise ValueError("ambiguous duplicate pytest suffixes")
    return ids


def native_map(selectors, generated):
    projected = {}
    for identity in generated:
        projected.setdefault(identity.split(maxsplit=1)[0], []).append(identity)
    if len(set(selectors)) != len(selectors) or set(selectors) != projected.keys():
        raise ValueError("complete native projection does not equal the published aliases")
    return {selector: projected[selector] for selector in selectors}


def pytest_pin(wheels, version="8.3.5"):
    wheel, = [row for row in wheels if Path(row["path"]).name == f"pytest-{version}-py3-none-any.whl"]
    file = Path(wheel["path"])
    read(file, wheel["sha256"])
    with ZipFile(file) as package:
        first, second = (package.read(name) for name in ("_pytest/python.py", "_pytest/compat.py"))
    methods = {node.name: ast.unparse(node) for raw in (first, second) for node in ast.walk(ast.parse(raw))
               if isinstance(node, ast.FunctionDef)}
    fragments = {
        "_resolve_ids": ("zip(parameterset.values, self.argnames)", "'-'.join"),
        "_idval_from_value": ("_ascii_escaped_by_config", "__name__"),
        "_idval_from_argname": ("str(argname) + str(idx)",),
        "ascii_escaped": ("encode('unicode_escape').decode('ascii')",),
    }
    if any(snippet not in methods[method] for method, snippets in fragments.items() for snippet in snippets):
        raise ValueError("pinned pytest identity behavior differs")
    return {"wheel_sha256": wheel["sha256"], "pytest_python_sha256": digest(first),
            "pytest_compatibility_sha256": digest(second)}


async def audit():
    source = WORK / "repository-expansion-acquisition"
    rows = json.loads(read(source / "index.json", INDEX))
    row, = [item for item in rows if item["input"]["task_id"] == CASE]
    raw = json.loads(read(source / "archives/conan-io__conan-19735_interface/row.json", ROW))
    if raw["base_commit"] != REVISION or row["source_revision"] != REVISION:
        raise ValueError("source revision differs")
    wheel_lock, wheels = wheel_probe_assets()
    task, truth, reference, original, _ = bind(row, source / "transport", wheels)
    overlay = archive_files(truth.tests.read(), large=True)
    body = overlay[TEST]
    previous = archive_files(truth.source.read(), large=True)
    prospective_config = [text for name, text in previous.items()
                          if name in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py")
                          or (name.endswith("/conftest.py") and TEST.startswith(name.removesuffix("conftest.py")))]
    if any(b"pytest_make_parametrize_id" in text or b"disable_test_id_escaping" in text
           for text in prospective_config):
        raise ValueError("custom native ID rules require review")

    legacy = [selector for selector in truth.pass_to_pass if "[" in selector and not selector.endswith("]")]
    generated = [identity for name in MODULES for identity in native_ids(body, name)]
    mapping = native_map(legacy, generated)
    failure, = raw["FAIL_TO_PASS"]
    issue, = mapping[failure]
    if set(truth.pass_to_pass) != {*raw["FAIL_TO_PASS"], *raw["PASS_TO_PASS"], row["protected_guard"]}:
        raise ValueError("protected publisher roles differ")
    compiler, banner, expected = declared_cases(body, MODULES[1])[-1]
    if (compiler != "detect_emcc_compiler" or not banner.startswith("shared:INFO: ")
            or "\n" not in banner or expected != ("emcc", "4.0.22", "emcc")
            or issue != native_ids(body, MODULES[1])[-1]):
        raise ValueError("the added multiline regression no longer has the expected binding")

    selected = [native for selector in truth.pass_to_pass for native in mapping.get(selector, [selector])]
    if len(selected) != len(set(selected)) or len(selected) != 30:
        raise ValueError("unexpected native observation count")
    corrected = SuiteTruthV6.model_validate(truth.model_dump(mode="json") | {"pass_to_pass": selected})
    dry = []
    for role, response, field in (("reference", reference, "reference_archive_sha256"),
                                  ("original", original, "fault_archive_sha256")):
        statuses = dict.fromkeys(selected, "PASSED")
        if role == "original":
            statuses.update({issue: "FAILED", row["protected_guard"]: "FAILED"})

        async def substitute(payload, *, archive_pin=row[field], role_name=role, observed=statuses):
            if payload["archive_sha256"] != archive_pin:
                raise ValueError("selector coverage changed the executable archive")
            dry.append({"role": role_name, "payload_sha256": content_digest(payload),
                        "archive_sha256": payload["archive_sha256"],
                        "expected_pass": sum(value == "PASSED" for value in observed.values()),
                        "expected_fail": sum(value == "FAILED" for value in observed.values())})
            return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
                "statuses": observed, "exit_code": int(role_name == "original"),
            }

        grade = await grade_suite_output(task.model_dump(mode="json"), corrected.model_dump(mode="json"),
                                        response, substitute)
        if grade.quality_score != float(role == "reference"):
            raise ValueError("ordinary grader rejects the proposed observations")
    return {
        "schema_version": "aeep.c13.conan-native-selector-preflight.v1",
        "source_revision": REVISION, "candidate_index_sha256": INDEX, "publisher_row_sha256": ROW,
        "protected_test_sha256": digest(body),
        "protected_overlay_sha256": truth.tests.sha256, "source_sha256": task.source_sha256,
        "pytest_8_3_5": pytest_pin(wheels), "retained_wheel_review_sha256": wheel_lock,
        "published_selector_count": len(raw["PASS_TO_PASS"]) + len(raw["FAIL_TO_PASS"]),
        "original_required_selector_count": len(truth.pass_to_pass), "covered_native_count": len(selected),
        "truncated_aliases": len(mapping), "aliases_covering_multiple_tests": sum(len(v) > 1 for v in mapping.values()),
        "additional_original_preservation_instances": len(selected) - len(truth.pass_to_pass),
        "emcc_regression_unique": True,
        "ordinary_callback_rehearsals": dry, "rehearsal_uses_substituted_test_results": True,
        "runtime_verified": False, "actual_grade": None, "formal_assignments": 0, "model_turns": 0,
        "protected_upstream_executions": 0,
    }, {"native_ids": selected, "alias_mapping": mapping, "regression_id": issue,
        "corrected_truth": corrected.model_dump(mode="json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-selection", type=Path, required=True)
    args = parser.parse_args()
    result, private = asyncio.run(audit())
    with args.private_selection.open("x") as output:
        output.write(json.dumps(private, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
