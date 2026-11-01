"""First-party protocol fixtures; no upstream implementation executes."""

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep_toolkit import ase_child, ase_contract


def test_pinned_source_check_rejects_version_and_source_drift(tmp_path, monkeypatch):
    path = tmp_path / "module.py"
    path.write_text("owned source fixture")
    monkeypatch.setattr(
        ase_contract,
        "ASE_SOURCE_FILES",
        {"module.py": hashlib.sha256(path.read_bytes()).hexdigest()},
    )
    monkeypatch.setattr(
        ase_contract,
        "distribution",
        lambda _: SimpleNamespace(version="0.7.0", locate_file=lambda _: path),
    )
    ase_contract.verify_runtime_source()
    path.write_text("changed")
    with pytest.raises(ValueError, match="source changed"):
        ase_contract.verify_runtime_source()
    monkeypatch.setattr(ase_contract, "distribution", lambda _: SimpleNamespace(version="0.8.0"))
    with pytest.raises(ValueError, match="version"):
        ase_contract.verify_runtime_source()


def test_source_map_matches_preserved_upstream_inventory():
    root = Path(__file__).resolve().parents[1]
    expected = json.loads((root / "integrations/toolkit/stack.json").read_text())["evaluator"][
        "source_files"
    ]
    assert expected == ase_contract.ASE_SOURCE_FILES
    assert len(expected) == 16


@pytest.mark.parametrize("fault", [None, "slot", "token", "unknown-prompt"])
def test_child_uses_agent_harness_for_grade_certificates(tmp_path, monkeypatch, fault):
    called = []
    monkeypatch.chdir(tmp_path)
    request = {
        "slots": ["0"],
        "run_token": "a" * 64,
        "skill_name": "fixture",
        "response_timeout": 1,
    }
    if fault == "slot":
        request["slots"] = ["2"]
    responses = tmp_path / "responses"
    responses.mkdir()
    response = {
        "slot": "0",
        "run_token": "b" * 64 if fault == "token" else "a" * 64,
        "trial_ref": "c" * 64,
        "canonical_valid": True,
    }
    (responses / "0.json").write_text(json.dumps(response))

    class AgentHarness:
        pass

    harnesses = SimpleNamespace(AgentHarness=AgentHarness, HARNESSES={})
    models = SimpleNamespace(AgentType=SimpleNamespace(CODEX="codex"), TimingData=lambda **k: k)

    class Runner:
        def __init__(self, skill, suite, workspace, agents, **kwargs):
            assert kwargs["grader_model"] == "" and kwargs["agent_max_retries"] == 0
            assert kwargs["concurrency"] == 1 and kwargs["with_baseline"] is False
            assert (
                kwargs["pre_run_commands"]
                == kwargs["post_grade_commands"]
                == kwargs["post_run_commands"]
                == []
            )
            assert skill == tmp_path / "candidate/fixture" and agents == ["codex"]
            self.folder = workspace / "fixture-workspace/iteration-1"

        def run(self):
            selected = harnesses.HARNESSES["codex"]
            assert issubclass(selected, AgentHarness) and selected.version_command is None
            instance = selected()
            with pytest.raises(ValueError, match="unsupported"):
                instance.build_command("prompt", tmp_path)
            with pytest.raises(ValueError, match="unsupported"):
                instance.parse_output("", "")
            output_dir = self.folder / "eval-0/codex/with_skill/outputs"
            output, timing, stdout, stderr = instance.run(
                "1" if fault == "unknown-prompt" else "0", output_dir
            )
            assert json.loads(output) == response and timing == {"exit_code": 0}
            assert output == stdout and stderr == ""
            (output_dir.parent / "grading.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "passed": 1,
                            "failed": 0,
                            "total": 1,
                            "pass_rate": 1.0,
                            "skipped": 0,
                        }
                    }
                )
            )
            called.append(True)
            return self.folder

    modules = {
        "agent_skill_eval.harnesses": harnesses,
        "agent_skill_eval.models": models,
        "agent_skill_eval.runner": SimpleNamespace(EvalRunner=Runner),
    }
    monkeypatch.setattr(
        ase_child, "importlib", SimpleNamespace(import_module=lambda name: modules[name])
    )
    monkeypatch.setattr(ase_child, "verify_runtime_source", lambda: None)
    output = io.StringIO()
    monkeypatch.setattr(
        ase_child,
        "sys",
        SimpleNamespace(
            stdin=SimpleNamespace(buffer=io.BytesIO(json.dumps(request).encode())),
            stdout=output,
            stderr=io.StringIO(),
        ),
    )
    if fault:
        with pytest.raises(ValueError):
            ase_child.main()
        assert not called
    else:
        ase_child.main()
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        assert [m["kind"] for m in messages] == ["trial", "done"]
        assert messages[-1]["upstream_timing_is_compatibility_only"] is True


def test_child_rejects_large_request_before_dispatch(monkeypatch):
    monkeypatch.setattr(ase_child, "verify_runtime_source", lambda: None)
    monkeypatch.setattr(
        ase_child, "importlib", SimpleNamespace(import_module=lambda _: SimpleNamespace())
    )
    monkeypatch.setattr(
        ase_child, "sys", SimpleNamespace(stdin=SimpleNamespace(buffer=io.BytesIO(b" " * 1048577)))
    )
    with pytest.raises(ValueError, match="bounds"):
        ase_child.main()
