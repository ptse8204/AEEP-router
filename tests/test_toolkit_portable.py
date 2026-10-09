"""Synthetic sharing checks, not independent evidence or developer verification."""

import hashlib
import json

import pytest
from test_toolkit_reporting import bundle

from aeep_toolkit.models import DeveloperIdentity
from aeep_toolkit.reporting import portable_summary


def test_portable_minimizes_private_names_and_keeps_measurement_unknowns():
    value = bundle(task_family="PRIVATE_PROJECT", host_version="PRIVATE_HOST")
    result = portable_summary(value)
    text = json.dumps(result)
    assert "PRIVATE_" not in text and "example.org" not in text
    assert result["document"]["source"] is None
    assert result["document"]["trust"] == "unverified_supplied_records"
    assert not result["document"]["publication_performed"]
    assert all(
        f["arms"]["treatment"]["metrics"]["tokens"]["complete_total"] is None
        for c in result["document"]["cohorts"]
        for f in c["families"]
    )
    assert (
        result["content_sha256"]
        == hashlib.sha256(
            json.dumps(
                result["document"],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
    )
    assert portable_summary(value) == result


def test_support_assertion_requires_explicit_source_disclosure_and_exact_binding():
    value = bundle()
    developer = DeveloperIdentity(
        source=value.candidate,
        identity="fixture",
        assertion_ref="f" * 64,
        support_url="https://github.com/sponsors/fixture",
        support_kind="donation",
    )
    with pytest.raises(ValueError):
        portable_summary(value, developer=developer)
    result = portable_summary(value, developer=developer, disclose_source=True)
    assert result["document"]["developer"]["status"] == "operator_supplied_unverified"
    assert result["document"]["developer"]["assertion"]["support_kind"] == "donation"
    developer.source = developer.source.model_copy(update={"artifact_sha256": "f" * 64})
    with pytest.raises(ValueError):
        portable_summary(value, developer=developer, disclose_source=True)


def test_minimized_export_preserves_incompatible_cohorts():
    result = portable_summary(bundle(model="different"))["document"]
    assert len(result["cohorts"]) == 2
    assert len({c["scope_sha256"] for c in result["cohorts"]}) == 2
    assert all(c["families"][0]["observed_pairs"] == 0 for c in result["cohorts"])


def test_cli_sharing_preview_is_local_and_does_not_mutate_inputs(
    tmp_path, capsys, monkeypatch
):
    import socket
    import subprocess

    from aeep_toolkit.cli import main

    path = tmp_path / "evidence.json"
    path.write_text(bundle().model_dump_json())
    before = path.read_bytes()

    def denied(*args, **kwargs):
        raise AssertionError("preview executed or accessed network")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    assert main(["export-preview", "--evidence", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == portable_summary(bundle())
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == [path]


def test_catalog_distinguishes_working_adapters_from_unqualified_options(capsys):
    from aeep_toolkit.cli import main

    assert main(["list", "full"]) == 0
    value = json.loads(capsys.readouterr().out)
    entries = {item["id"]: item for item in value["catalog"]}
    assert value["selected"] == []
    assert entries["agent-skill-eval"]["qualification"] == "scripted_engineering_only"
    assert entries["agent-skill-eval"]["installed"] is None
    assert entries["aeep-evaluator"]["qualification"] == "software_tests_only"
    assert entries["waza"]["status"] == "blocked"
