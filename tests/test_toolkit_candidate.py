"""Candidate bytes copied to a worker must be exactly the bytes in its identity."""

import json
import os
import sys

import pytest
from test_toolkit_runtime_install import installer_fixture_capacity as installer_fixture_capacity

from aeep_toolkit.candidate import inspect
from aeep_toolkit.cli import main

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="candidate reader requires POSIX no-follow file support"
)


def test_nested_excluded_bytes_never_enter_staged_payload(tmp_path):
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_text("Synthetic instructions")
    (root / "resources").mkdir()
    (root / "resources/data.txt").write_text("included")
    (root / "resources/evals").mkdir()
    (root / "resources/evals/answer.txt").write_text("excluded oracle canary")
    first = inspect(root)
    (root / "resources/evals/answer.txt").write_text("changed excluded bytes")
    assert inspect(root).sha256 == first.sha256
    (root / "resources/data.txt").write_text("changed included bytes")
    assert inspect(root).sha256 != first.sha256
    first.stage(tmp_path / "staged")
    assert (tmp_path / "staged/resources/data.txt").read_text() == "included"
    assert not (tmp_path / "staged/resources/evals").exists()
    assert inspect(tmp_path / "staged").sha256 == first.sha256
    with pytest.raises(ValueError):
        first.stage(tmp_path / "staged")


@pytest.mark.parametrize(
    "kind", ["symlink", "hardlink", "fifo", "credentials", "case_collision", "missing_skill"]
)
def test_unsafe_payload_stops_before_staging(tmp_path, kind):
    (tmp_path / "SKILL.md").write_text("fixture")
    if kind == "symlink":
        (tmp_path / "link").symlink_to(tmp_path / "SKILL.md")
    elif kind == "hardlink":
        os.link(tmp_path / "SKILL.md", tmp_path / "linked")
    elif kind == "fifo":
        os.mkfifo(tmp_path / "pipe")
    elif kind == "credentials":
        (tmp_path / "auth.json").write_text("never read")
    elif kind == "case_collision":
        # Also rejects a single noncanonical Skill.md spelling on case-insensitive hosts.
        (tmp_path / "SKILL.md").rename(tmp_path / "Skill.md")
    else:
        (tmp_path / "SKILL.md").unlink()
    with pytest.raises(ValueError):
        inspect(tmp_path)


def test_cli_has_only_hashes_and_captured_mutation_is_rejected(tmp_path, capsys):
    (tmp_path / "SKILL.md").write_text("private skill text")
    assert main(["candidate", str(tmp_path / "SKILL.md")]) == 0
    data = capsys.readouterr().out
    assert "private skill text" not in data and json.loads(data)["executed"] is False
    payload = inspect(tmp_path)
    payload.files["../escape"] = b"bad"
    with pytest.raises(ValueError):
        payload.stage(tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_staged_cli_subject_excludes_answers_and_preserves_user_work(tmp_path, capsys, installer_fixture_capacity):
    from aeep.assessment.models import AssessmentSubject
    from aeep.assessment.repository import AssessmentRepository
    from aeep.models import Manifest
    from aeep.store import ReceiptStore

    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: owned-fixture\ndescription: public local instructions\n---\n"
    )
    (skill / "evals").mkdir()
    (skill / "evals" / "answer.txt").write_text("protected answer fixture must not be inspected")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        Manifest(database=str(tmp_path / "canonical.sqlite3"), executors=[]).model_dump_json()
    )
    target = tmp_path / "staged"
    assert main(["candidate", str(skill), "--stage", str(target), "--manifest", str(manifest)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["subject_ref"] and value["setup_cost_ref"] and not (target / "evals").exists()
    assert value["candidate_sha256"] == inspect(target).sha256
    assert not value["execution_authorized"]
    store = ReceiptStore(tmp_path / "canonical.sqlite3")
    try:
        repo = AssessmentRepository(store)
        subject = AssessmentSubject.model_validate(repo.get("subject", value["subject_ref"]))
        assert subject.dependency_digests == value["files"]
        assert (
            store._connection.execute("SELECT count(*) FROM assessment_grants").fetchone()[0] == 0
        )
        assert (
            store._connection.execute(
                "SELECT count(*) FROM assessment_records WHERE kind='setup_cost'"
            ).fetchone()[0]
            == 2
        )
    finally:
        store.close()
    (target / "user-notes.txt").write_text("preserve this")
    with pytest.raises(SystemExit):
        main(["candidate", str(skill), "--stage", str(target), "--manifest", str(manifest)])
    assert (target / "user-notes.txt").read_text() == "preserve this"


def test_credential_directory_is_rejected_before_its_files_are_read(tmp_path, monkeypatch):
    (tmp_path / "SKILL.md").write_text("fixture")
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh/id_rsa").write_text("synthetic secret canary")
    from aeep_toolkit import cli

    original = cli.read_bytes

    def read(path):
        assert ".ssh" not in path.parts, "credential directory was traversed"
        return original(path)

    monkeypatch.setattr(cli, "read_bytes", read)
    with pytest.raises(ValueError, match="credential-state"):
        inspect(tmp_path)
