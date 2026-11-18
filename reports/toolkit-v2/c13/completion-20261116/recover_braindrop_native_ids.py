"""Resolve whitespace-truncated publisher selectors against unchanged literal parameters."""

import ast
import asyncio
from collections import Counter
import json
from pathlib import Path
from zipfile import ZipFile

import check_braindrop_contract as braindrop
from audit_staged_repository_graders import wheel_probe_assets
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import SuiteTruthV6, archive_files, grade_suite_output

runner = braindrop.runner
ROOT, HERE, WORK = braindrop.ROOT, braindrop.HERE, braindrop.WORK
TARGET = braindrop.TARGET
ACQUISITION = WORK / "repository-expansion-acquisition"
TEST = "tests/unit/test_raindrop.py"
RAW_ROW = ACQUISITION / "archives/davep__braindrop-96/row.json"
ROW_SHA256 = "45417c2d9bf361324b5a41f6b659a0cd4f35395c8499d4489067e8824838ff13"


def truncated(identity):
    return "[" in identity and not identity.endswith("]") and "::" in identity


def check_pinned_id_algorithm():
    _, wheels = wheel_probe_assets()
    record, = [wheel for wheel in wheels if Path(wheel["path"]).name == "pytest-8.3.5-py3-none-any.whl"]
    with ZipFile(record["path"]) as wheel:
        body = wheel.read("_pytest/python.py")
    cls, = [node for node in ast.parse(body).body if isinstance(node, ast.ClassDef) and node.name == "IdMaker"]
    methods = {node.name: ast.unparse(node) for node in cls.body if isinstance(node, ast.FunctionDef)}
    required = {
        "_idval": ("self._idval_from_value", "self._idval_from_argname"),
        "_idval_from_value": ("_ascii_escaped_by_config", "return str(val)", "return None"),
        "_idval_from_argname": ("str(argname) + str(idx)",),
        "_resolve_ids": ("join", "zip(parameterset.values, self.argnames)"),
    }
    if any(fragment not in methods[key] for key, fragments in required.items() for fragment in fragments):
        raise ValueError("pinned pytest identity algorithm differs")
    return {"wheel_sha256": record["sha256"], "id_maker_file_sha256": braindrop.contracts.digest(body)}


def literal_ids(tree, funcs):
    output = []
    for name in sorted(funcs):
        declare, = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        decorator, = declare.decorator_list
        if not isinstance(decorator, ast.Call) or ast.unparse(decorator.func) != "mark.parametrize" or decorator.keywords:
            raise ValueError("only the verified uncustomized literal parameter type is supported")
        fields, cases = map(ast.literal_eval, decorator.args)
        fields = tuple(part.strip() for part in fields.split(","))
        for index, val in enumerate(cases):
            values = (val,) if len(fields) == 1 else val
            parts = []
            for field, item in zip(fields, values, strict=True):
                if isinstance(item, str):
                    if not item.isascii() or any(ord(ch) < 32 or ord(ch) == 127 for ch in item):
                        raise ValueError("only printable ASCII parameter strings in the selected cases")
                    parts.append(item)
                elif item is None or isinstance(item, (bool, int)):
                    parts.append(str(item))
                elif isinstance(item, tuple):
                    parts.append(f"{field}{index}")
                else:
                    raise ValueError("unchecked parameter type")
            output.append(f"{TEST}::{name}[{'-'.join(parts)}]")
    if len(output) != len(set(output)):
        raise ValueError("pytest duplicate suffixes would need a separate review")
    return output


def choose_matches(aliases, generated, existing):
    matches = {}
    for label in aliases:
        possible = [identity for identity in generated if identity.split(maxsplit=1)[0] == label]
        if len(possible) != 1 or possible[0] in existing or possible[0] in matches.values():
            raise ValueError("publisher selector has ambiguous or repeated native matches")
        matches[label] = possible[0]
    return matches


def screen_retained_expansion():
    review = braindrop.contracts.pinned(HERE / "repository-expansion-acquisition-result.json")
    rows = json.loads(braindrop.contracts.read(ACQUISITION / "index.json", review["candidate_index_sha256"]))
    affected = {}
    for row in rows:
        case = row["input"]["task_id"]
        if "protected_assets" in row:
            pin, expected = row["protected_assets"]["required.json"], "published_"
        else:
            pin, expected = row["required_identities"], ""
        path = ACQUISITION / "transport" / "protected" / case / "required.json"
        required = json.loads(braindrop.contracts.read(path, pin["sha256"]))
        counts = {role: sum(truncated(identity) for identity in required[expected + role])
                  for role in ("fail_to_pass", "pass_to_pass")}
        if any(counts.values()):
            affected[case] = counts
    return {"publisher_rows_screened": len(rows), "truncated_candidate_selectors": affected}


async def build():
    braindrop.configure()
    original_review = runner.get(runner.REVIEW)
    calculated, spec, environment, [case] = await runner.review_fields()
    if calculated != {k: v for k, v in original_review.items() if k != "expires_at"}:
        raise ValueError("first-attempt scope changed")
    parent = SuiteTruthV6.model_validate(case["truth"])
    raw_row = json.loads(braindrop.contracts.read(RAW_ROW, ROW_SHA256))
    designated = {row for row in parent.pass_to_pass if truncated(row)}
    cutoff = read_diagnostic()
    if (len(designated) != 11 or designated != {row for row in raw_row["PASS_TO_PASS"] if truncated(row)}
            or len(parent.pass_to_pass) - cutoff["matched_required"] != len(designated)):
        raise ValueError("exact publisher truncation and contained collection counts do not agree")
    public = archive_files(parent.source.read(), large=True)
    overlay = archive_files(parent.tests.read(), large=True)
    body = overlay[TEST] if TEST in overlay else public[TEST]
    abi = check_pinned_id_algorithm()
    affected = {selector.rsplit("::", 1)[-1].split("[", 1)[0] for selector in designated}
    expanded = literal_ids(ast.parse(body), affected)
    fixed = choose_matches(sorted(designated), expanded, set(parent.pass_to_pass) - designated)
    passed = [fixed.get(label, label) for label in parent.pass_to_pass]
    assert len(set(passed)) == len(passed) == 63
    try:
        choose_matches(sorted(designated), [*expanded, fixed[min(designated)] + " copied"], set())
    except ValueError:
        ambiguous_rejected = True
    else:
        raise AssertionError("ambiguous alias was accepted")
    old_expected = runner.expected_statuses
    context = SuiteTruthV6.model_validate(case["truth"] | {"pass_to_pass": passed})
    corrected = case | {"truth": context.model_dump(mode="json")}
    old_roles = original_review["launches"]
    observations = []
    for role, old in zip(runner.ROLES, old_roles, strict=True):
        expected = {fixed.get(label, label): status for label, status in old_expected(case["truth"], role).items()}

        async def verify_payload(payload):
            if content_digest(payload) != old["payload_sha256"] or payload["archive_sha256"] != old["archive_sha256"]:
                raise ValueError("a selector correction changed the executable task payload")
            observations.append({"role": role, "payload_sha256": old["payload_sha256"],
                                 "protected_archive_sha256": old["archive_sha256"],
                                 "expected_counts": dict(Counter(expected.values()))})
            return {k: payload[k] for k in ("archive_sha256", "python", "pytest")} | {
                "statuses": expected, "exit_code": int(role == "original"),
            }

        grade = await grade_suite_output(corrected["input"], corrected["truth"], corrected["roles"][role], verify_payload)
        if grade.quality_score != float(role == "reference"):
            raise ValueError("protected ordinary score contract differs")
    output = {
        "schema_version": "aeep.c13.braindrop-native-selector-correction.v1",
        "case": braindrop.CASE, "original_case_fingerprint": content_digest(case),
        "corrected_case_fingerprint": content_digest(corrected),
        "original_review_sha256": runner.file_digest(runner.REVIEW), "publisher_row_sha256": ROW_SHA256,
        "private_test_body_sha256": braindrop.contracts.digest(body), "pinned_pytest": abi,
        "original_scope_collect_counts": cutoff, "replacement_identities": fixed,
        "identities_retained": len(passed), "ambiguous_alias_control_rejected": ambiguous_rejected,
        "callback_checks_substituted": observations, "retained_expansion_screen": screen_retained_expansion(),
        "environment": content_digest(environment), "observer": content_digest(spec), "actual_grade": None,
        "new_upstream_verifier_executions": 0, "model_turns": 0, "formal_assignments": 0,
    }
    return output, corrected, fixed


def read_diagnostic():
    result = runner.get(TARGET / "braindrop-collection-result.json")
    values = result["observations"]
    if result["grade"] or not result["container_absent"] or not values["native_report"] or values["pytest_exit"] != 0:
        raise ValueError("collection-only diagnostic no longer verifies")
    if values["counts"]["selected_ids"] != 63 or values["counts"]["native_ids"] != 63:
        raise ValueError("the retained diagnostic did not collect all protected identities")
    return values["counts"]


if __name__ == "__main__":
    print(json.dumps(asyncio.run(build())[0], indent=2, sort_keys=True, allow_nan=False))
