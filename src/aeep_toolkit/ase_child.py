"""Pinned ASE scheduler child. No model, credential or execution authority lives here.

The real AgentHarness forwards opaque trial slots to the canonical parent. The
parent executes and protects task grading. ASE's deterministic JSON assertion
checks that grade certificate; it is not a second independent task verifier.
Upstream mandatory timing defaults are compatibility artifacts, never telemetry.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from .ase_contract import verify_runtime_source


def main() -> None:
    verify_runtime_source()
    raw = sys.stdin.buffer.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("scheduler request exceeds bounds")
    request = json.loads(raw)
    if (
        set(request) != {"slots", "run_token", "skill_name", "response_timeout"}
        or not 1 <= len(request["slots"]) <= 6
        or request["slots"] != [str(i) for i in range(len(request["slots"]))]
    ):
        raise ValueError("invalid scheduler slots")
    harnesses = importlib.import_module("agent_skill_eval.harnesses")
    models = importlib.import_module("agent_skill_eval.models")
    runner_module = importlib.import_module("agent_skill_eval.runner")
    AgentHarness = harnesses.AgentHarness

    root = Path.cwd()
    skill = root / "candidate" / request["skill_name"]
    channel = sys.stdout

    class ControlledAgentHarness(AgentHarness):  # type: ignore[misc, valid-type]
        # Optional upstream SDK has no dependency in the minimal AEEP installation.
        agent_type = models.AgentType.CODEX
        version_command = None  # Worker identity is verified by the parent, not a host CLI probe.
        supports_reasoning_effort = False

        def build_command(self, prompt: str, output_dir: Path) -> list[str]:
            raise ValueError(
                "native Codex launch is unsupported; use canonical controlled dispatch"
            )

        def parse_output(self, stdout: str, stderr: str) -> tuple[str, Any]:
            raise ValueError("native Codex usage parsing is unsupported; use canonical receipts")

        def run(self, prompt: str, output_dir: Path) -> tuple[str, Any, str, str]:
            if prompt not in request["slots"]:
                raise ValueError("upstream requested an unreviewed trial")
            channel.write(
                json.dumps({"kind": "trial", "slot": prompt, "run_token": request["run_token"]})
                + "\n"
            )
            channel.flush()
            response_path = root / "responses" / (prompt + ".json")
            deadline = time.monotonic() + request["response_timeout"]
            while not response_path.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("canonical parent did not finish the trial")
                time.sleep(0.02)
            if response_path.is_symlink() or response_path.stat().st_size > 65536:
                raise ValueError("invalid canonical response")
            response = json.loads(response_path.read_bytes())
            if (
                set(response) != {"run_token", "slot", "trial_ref", "canonical_valid"}
                or response["run_token"] != request["run_token"]
                or response["slot"] != prompt
                or type(response["canonical_valid"]) is not bool
            ):
                raise ValueError("canonical response identity differs")
            output = json.dumps(response)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "stdout.log").write_text(output)
            (output_dir / "stderr.log").write_text("")
            # ASE0.7.0 cannot express all missing token categories. None of this
            # required compatibility object is imported as measured usage.
            return output, models.TimingData(exit_code=0), output, ""

    harnesses.HARNESSES[models.AgentType.CODEX] = ControlledAgentHarness
    with contextlib.redirect_stdout(sys.stderr):
        runner = runner_module.EvalRunner(
            skill,
            skill / "evals/evals.json",
            root / "upstream",
            [models.AgentType.CODEX],
            concurrency=1,
            with_baseline=False,
            grader_model="",
            agent_max_retries=0,
            runs=1,
            pre_run_commands=[],
            post_grade_commands=[],
            post_run_commands=[],
        )
        iteration = runner.run()
    grades = []
    for slot in request["slots"]:
        folder = iteration / ("eval-" + slot) / "codex" / "with_skill"
        grading = json.loads((folder / "grading.json").read_bytes())
        grades.append({"slot": slot, "summary": grading["summary"]})
    channel.write(
        json.dumps(
            {"kind": "done", "grades": grades, "upstream_timing_is_compatibility_only": True}
        )
        + "\n"
    )
    channel.flush()


if __name__ == "__main__":
    main()
