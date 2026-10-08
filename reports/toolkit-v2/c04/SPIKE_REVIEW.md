# C04 agent-skill-eval engineering spike

Status: prepared for review; upstream code has not been executed. This spike uses
the actual pinned upstream CLI, runner, fake harness and deterministic graders.
It does not test a model or establish controlled-worker conformance.

## Exact scope

- Source: agent-skill-eval 0.7.0, commit
  `59de161f657b82bfaf8f6abe83dfff38552deb21`. All 16 package source files and
  the upstream CLI smoke test are hashed in
  [the source record](agent-skill-eval-source-review.json). No source patches.
- Dependencies: five of six declared dependencies already exist in the host Python
  environment. OpenAI is absent but imported by the grader module even when model
  grading is disabled. [The wheel preview](spike-dependency-preview.json) and
  [hash lock](spike-requirements.txt) bind nine missing/updated wheels. Install only
  into a private scratch virtual environment with read-only access to the existing
  Python packages. Do not change the host environment or project dependencies.
- Scratch root: create a fresh directory with prefix `/tmp/aeep-ase-c04-`. Allow
  up to 500 MiB there and check the host's 50 GiB reserve before installation.
  Dependency metadata resolution downloaded small wheels to pip's cache; no
  installation occurred. The last observed available space was 95,837,316 KiB.
- Input: the two synthetic cases in `spike-fixtures/format-json/evals/evals.json`,
  with the accompanying synthetic skill. Each case runs once in both arms.
  No skill invocation is forced; upstream's fake implementation makes the
  formatting result depend on fixture skill presence. That is an engineered
  fixture outcome, not evidence of benefit from a real model.
- Execution: local Git creates disposable repositories. Disable model grading,
  retries, hooks, repository cloning and provider setup. Empty the inherited
  environment, use a fresh HOME, disable dotenv loading and global Git config.
  Run the upstream child under macOS sandbox-exec with network access and reads
  of the real user home denied; allow writes only beneath the fresh scratch root.
  Verify those restrictions with synthetic probes before invoking upstream.
  This engineering guard is not the required separate-container comparison boundary.
- Limits: two minutes per CLI command, no credentials, no paid calls, no Docker,
  no services, no user skill execution and no global configuration changes.
  Stop on source/hash drift or failed preflight; do not silently weaken the guard.
- Outputs: inspect upstream run metadata, grading, timing and trajectories, plus
  its Markdown report. Retain only synthetic artifacts and command/status hashes.
  Upstream fake token/time/cost fields stay synthetic; never import them as real
  measurements. Cleanup removes only the recorded scratch environment.

## Commands after approval

Create the private environment with `python3 -m venv --system-site-packages`, then
use its Python to install the hash-locked wheels with
`-m pip install --only-binary=:all: --no-deps --require-hashes -r spike-requirements.txt`.
The upstream source is loaded through its pinned `src` path, without installing
its build backend. Paths below are placeholders beneath the new scratch root.

```text
python -B -m agent_skill_eval run --skill INPUT/format-json --evals INPUT/format-json/evals/evals.json --agent fake --workspace OUTPUT --grader-model "" --baseline --runs 1 --concurrency 1 --retries 0 --timeout 30
python -B -m agent_skill_eval report --workspace OUTPUT/format-json-workspace --format markdown
```

These are argv invocations, not shell hooks. Before execution, copy the reviewed
inputs/source into scratch and verify every source and wheel hash. The small
AEEP adapter will be based on these actual upstream outputs once available.

## Authority boundary

The original request and CONTINUATION.md require specific authority for executing
third-party software. Approval requested here covers only this pinned, fixture-only
spike and its private dependencies. It does not cover real Codex/Claude/OpenCode
execution, candidate plugins, cloud services, model spending or release.

Failure and timeout handling, missing telemetry, controlled real-host execution
and the full AEEP adapter remain C04 acceptance work after this first spike.
