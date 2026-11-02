"""Synthetic Cisco replies exercise the bridge; no scanner execution claim."""

import base64
import json
from subprocess import CompletedProcess

import pytest

from aeep_toolkit import scanner_worker
from aeep_toolkit.candidate import identity

REAL_RUNTIME_IDENTITY = scanner_worker.runtime_identity


@pytest.fixture(autouse=True)
def reviewed_runtime_substitute(monkeypatch):
    monkeypatch.setattr(
        scanner_worker,
        "runtime_identity",
        lambda: {
            "scanner_version": "2.2.1",
            "scanner_artifact_sha256": scanner_worker.SCANNER_ARTIFACT,
            "scanner_source_files_verified": 1,
        },
    )


def request():
    files = {
        "SKILL.md": b"---\nname: fixture\ndescription: synthetic scan input\n---\nRead public data.\n"
    }
    return {
        "files": {k: base64.b64encode(v).decode() for k, v in files.items()},
        "candidate_sha256": identity(files),
        "implementation_source": "a" * 64,
        "check": "static_scan",
    }


def reply(**changes):
    return (
        dict(
            findings_count=1,
            findings=[{"id": "fixture-high", "severity": "HIGH"}],
            analyzers_failed=[],
            analyzers_used=["static"],
        )
        | changes
    )


def test_scanner_bridge_uses_exact_cli_and_minimizes_data(tmp_path, monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert set(kwargs["env"]) == {"HOME", "PATH", "TMPDIR", "LANG", "PYTHONDONTWRITEBYTECODE"}
        return CompletedProcess(
            argv, 1, json.dumps(reply()).encode(), b"private diagnostic omitted"
        )

    monkeypatch.setattr(scanner_worker.subprocess, "run", run)
    result = scanner_worker.scan(request(), tmp_path)
    assert calls[0][0][0] == scanner_worker.SCANNER and calls[0][0][-2:] == ["--format", "json"]
    assert "--use-llm" not in calls[0][0] and result["candidate_bytes_bound"] is True
    assert result["findings_count"] == result["high_or_critical"] == 1
    assert result["safety_verdict"] == "NOT_ESTABLISHED"
    assert "private diagnostic" not in json.dumps(result)
    assert result["findings"][0]["id"] == "fixture-high"
    assert "description" not in result["findings"][0]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("change", ["hash", "traversal", "duplicate", "secret", "missing_skill"])
def test_invalid_candidate_never_reaches_scanner(tmp_path, monkeypatch, change):
    value = request()
    if change == "hash":
        value["candidate_sha256"] = "b" * 64
    elif change == "traversal":
        value["files"]["../answer"] = base64.b64encode(b"data").decode()
    elif change == "duplicate":
        value["files"]["skill.md"] = value["files"]["SKILL.md"]
    elif change == "secret":
        value["files"]["auth.json"] = base64.b64encode(b"not a real credential").decode()
    else:
        value["files"] = {"readme.md": value["files"]["SKILL.md"]}
    monkeypatch.setattr(
        scanner_worker.subprocess, "run", lambda *a, **k: pytest.fail("unsafe scan")
    )
    with pytest.raises(ValueError):
        scanner_worker.scan(value, tmp_path)


@pytest.mark.parametrize(
    "data",
    [
        reply(analyzers_used=["LLMAnalyzer"]),
        reply(findings_count=True),
        reply(analyzers_used=[]),
        reply(findings_count=2),
    ],
)
def test_unknown_or_unrequested_analyzers_and_inconsistent_counts_are_rejected(
    tmp_path, monkeypatch, data
):
    monkeypatch.setattr(
        scanner_worker.subprocess,
        "run",
        lambda argv, **k: CompletedProcess(argv, 0, json.dumps(data).encode(), b""),
    )
    with pytest.raises(ValueError):
        scanner_worker.scan(request(), tmp_path)


def test_analyzer_failures_remain_visible(tmp_path, monkeypatch):
    data = reply(analyzers_failed=[{"analyzer": "bytecode", "error": "synthetic failure"}])
    monkeypatch.setattr(
        scanner_worker.subprocess,
        "run",
        lambda argv, **k: CompletedProcess(argv, 0, json.dumps(data).encode(), b""),
    )
    observed = scanner_worker.scan(request(), tmp_path)
    assert observed["failed_analyzers"] == 1
    assert observed["analyzer_failures"][0]["analyzer"] == "bytecode"
    assert "synthetic failure" not in json.dumps(observed)


def test_absent_optional_failure_field_matches_upstream_success_schema(tmp_path, monkeypatch):
    data = reply()
    data.pop("analyzers_failed")
    monkeypatch.setattr(
        scanner_worker.subprocess,
        "run",
        lambda argv, **k: CompletedProcess(argv, 0, json.dumps(data).encode(), b""),
    )
    assert scanner_worker.scan(request(), tmp_path)["analyzer_failures"] == []


def test_host_execution_is_refused(monkeypatch):
    monkeypatch.setattr(scanner_worker.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="nonroot Linux worker"):
        scanner_worker.main()


def test_installed_scanner_identity_uses_owned_artifact_bytes_without_import(tmp_path, monkeypatch):
    import hashlib
    import zipfile
    from types import SimpleNamespace

    artifact = tmp_path / "scanner.whl"
    package = tmp_path / "skill_scanner"
    package.mkdir()
    code = b'raise AssertionError("owned identity fixture must never be imported")\n'
    (package / "fixture.py").write_bytes(code)
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("skill_scanner/fixture.py", code)
    monkeypatch.setattr(scanner_worker, "SCANNER_WHEEL", artifact)
    monkeypatch.setattr(
        scanner_worker, "SCANNER_ARTIFACT", hashlib.sha256(artifact.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(
        scanner_worker,
        "distribution",
        lambda _: SimpleNamespace(version="2.2.1", locate_file=lambda name: tmp_path / name),
    )
    observed = REAL_RUNTIME_IDENTITY()
    assert observed["scanner_source_files_verified"] == 1
    (package / "fixture.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="installed source"):
        REAL_RUNTIME_IDENTITY()
