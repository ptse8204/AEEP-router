"""Repair the first-party namespace lookup and bind the unchanged upstream tests."""
import ast
import asyncio
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import check_expansion_contracts as contracts
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import SuiteTruthV6, archive_files, grade_suite_output, pack_files

ROOT, WORK, runner = contracts.ROOT, contracts.WORK, contracts.runner
TARGET = WORK / "c13-expansion-contracts-20261118"
OUTPUT = TARGET / "otel-namespace-repair"
CONFTEST = "opentelemetry-sdk/tests/conftest.py"
ORIGINAL = "PathFinder.find_spec(\".\".join(parts[:i + 1]), locations)"
CORRECTED = "PathFinder.find_spec(parts[i], locations)"
FUNCTION = "_aeep_snapshot_imports"


def inspect_resolver(before, after, public):
    def definition(source):
        node, = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name == FUNCTION]
        return ast.unparse(node)

    with TemporaryDirectory(dir=TARGET) as temporary:
        root = Path(temporary).resolve()
        placeholder = b"raise AssertionError('placeholder must never execute')\n"
        for name in public:
            if name.endswith(".py") and "/src/opentelemetry/" in name:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(placeholder)
        foreign = root / "shadow/opentelemetry"
        foreign.mkdir(parents=True)
        (foreign / "__init__.py").write_bytes(placeholder)
        prefix = ("from pathlib import Path\nimport sys\n"
                  "assert 'opentelemetry' not in sys.modules\n")
        inventory = {}
        for label, source, additional, modules, error in (
            ("baseline_missing_parent", before, "[]", "sys.modules", "KeyError: 'opentelemetry'"),
            ("corrected_namespace", after, "[]", "sys.modules", None),
            ("foreign_regular_package", after, f"[{str(foreign.parent)!r}]", "sys.modules",
             "RuntimeError: protected snapshot module missing"),
            ("preloaded_namespace", after, "[]", "{'opentelemetry.sdk': object()}",
             "RuntimeError: OpenTelemetry was loaded before the protected source binding"),
        ):
            process = subprocess.run(
                [sys.executable, "-I", "-S", "-B", "-c",
                 f"{prefix}{definition(source)}\n{FUNCTION}(Path({str(root)!r}), {additional}, {modules})\n"],
                env={}, capture_output=True, text=True, timeout=10,
            )
            if error is None:
                assert process.returncode == 0 and not process.stderr, process.stderr
            else:
                assert process.returncode != 0 and error in process.stderr.splitlines()[-1], process.stderr
            assert "placeholder must never execute" not in process.stderr
            inventory[label] = {"exit": process.returncode, "expected_failure": error}
    return inventory


async def stage():
    contracts.configure("opentelemetry")
    original_review = runner.get(runner.REVIEW)
    original_bytes = runner.file_digest(runner.REVIEW)
    original_scope, spec, environment, cases = await runner.review_fields()
    if original_scope != {key: value for key, value in original_review.items() if key != "expires_at"}:
        raise ValueError("original protected review differs")
    case, = cases
    truth = SuiteTruthV6.model_validate(case["truth"])
    public = archive_files(truth.source.read(), large=True)
    overlay = archive_files(truth.tests.read(), large=True)
    original = overlay[CONFTEST].decode()
    if original.count(ORIGINAL) != 1 or CORRECTED in original:
        raise ValueError("protected bootstrap structure changed")
    corrected = original.replace(ORIGINAL, CORRECTED, 1)
    assert corrected.replace(CORRECTED, ORIGINAL, 1) == original
    original_match = inspect_resolver(original, corrected, public)
    assert all(overlay[test] for test in truth.test_paths) and CONFTEST not in truth.test_paths
    original_overlay = {name: contracts.digest(body) for name, body in overlay.items()}
    overlay[CONFTEST] = corrected.encode()
    former, actual = original_overlay[CONFTEST], contracts.digest(overlay[CONFTEST])
    assert {name: contracts.digest(body) for name, body in overlay.items() if name != CONFTEST} == {
        name: pin for name, pin in original_overlay.items() if name != CONFTEST
    }
    archive = pack_files(overlay, large=True)
    path = OUTPUT / "corrected-tests.tar.gz"
    if not path.exists():
        OUTPUT.mkdir(mode=0o700, parents=True)
        path.write_bytes(archive)
        path.chmod(0o400)
    if path.is_symlink() or path.read_bytes() != archive:
        raise ValueError("previous staged overlay differs")
    new_truth = SuiteTruthV6.model_validate(case["truth"] | {
        "tests": {"path": str(path), "size_bytes": path.stat().st_size, "sha256": contracts.digest(archive)}
    })
    assert new_truth.model_dump(mode="json", exclude={"tests"}) == truth.model_dump(mode="json", exclude={"tests"})
    checked = []
    for role in runner.ROLES:
        async def rehearsal(payload):
            # Frame and verify with the ordinary coordinator. These replies are synthetic.
            code = int(role == "original")
            expected = runner.expected_statuses(case["truth"], role)
            checked.append({"role": role, "payload_sha256": content_digest(payload),
                            "archive_sha256": payload["archive_sha256"], "required_identities": len(expected)})
            return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
                "statuses": expected, "exit_code": code,
            }

        result = await grade_suite_output(case["input"], new_truth.model_dump(mode="json"),
                                         case["roles"][role], rehearsal)
        assert result.quality_score == float(role == "reference")
    condensed = {
        "schema_version": "aeep.c13.otel-namespace-repair.v1", "case": case["case_id"],
        "reviewed_source": contracts.SOURCE, "original_review_sha256": original_bytes,
        "original_protected_archive_sha256": truth.tests.sha256,
        "original_conftest_sha256": former, "corrected_conftest_sha256": actual,
        "corrected_protected_archive": {
            "path": path.relative_to(ROOT).as_posix(), "sha256": contracts.digest(archive), "bytes": len(archive)
        },
        "unchanged_upstream_protected_files": len(overlay) - 1, "required_identities": len(truth.pass_to_pass),
        "public_snapshot_sha256": truth.source.sha256,
        "retained_carrier": environment.container_image,
        "ordinary_observer_fingerprint": content_digest(spec),
        "static_resolver_checks": original_match, "ordinary_framing_with_substituted_observations": checked,
        "model_turns": 0, "grade_executed": False, "formal_cases_adopted": 0,
        "driver_sha256": runner.file_digest(Path(__file__)),
    }
    print(json.dumps(condensed, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    asyncio.run(stage())
