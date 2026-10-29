# Check a stopped assessment without replaying it

This short operator exercise checks whether the CLI makes status and recovery
discoverable. It uses the stopped artifact-format attempt. Its workers are gone;
the later comparison uses different assessment IDs. These commands do not start
models, rerun tasks, install software or delete retained images.

## 1. Inspect the stopped job

In Terminal, run:

```bash
cd /Users/edwintse/Documents/aeep-toolkit-v2
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m aeep.cli assess \
  --manifest /Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.json \
  --directory /Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments \
  status assessment_101c404ae8694a65be39084509a76990
```

The verified command reports `state: indeterminate`, `report_id: null` and
`error_code: interrupted`. This records the interrupted assessment orchestration;
it is not a successful comparison report. The separate canonical reconciliation
confirms all three actual task attempts completed and were cleaned up. Their
charges remain. Do not rerun this assessment to make its status look successful.

## 2. Find and use recovery

The command is `assess`, not `assessment`. Its recovery operation inspects the
named attempt stores and cleans only uncertain owned workers; it does not replay
tasks or refund allowances. It refuses to recover a live assessment worker.

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m aeep.cli assess \
  --manifest /Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.json \
  --directory /Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments \
  recover assessment_101c404ae8694a65be39084509a76990
```

For this reconciled stopped job, the implementation-agent check returned
`retained_attempt_ids: []` and `containers_removed: 0`. Your actual output is the
human-control evidence; an agent cannot supply it for you. Report any different
output or unclear step instead of guessing.

## 3. Locate the stop control

Use help to find the command without cancelling another assessment:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m aeep.cli assess \
  --manifest /Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.json \
  cancel --help
```

For an active named assessment, `cancel ASSESSMENT_ID` stops subsequent dispatch.
An in-flight turn may already have effects or finish. Cancellation does not undo
effects, remove receipts, reset counters or authorize retry. Recovery is separate.
Do not cancel another current job as part of this exercise.

## What to send back

Briefly report the status, `retained_attempt_ids`, `containers_removed`, and the
command you found for stopping future dispatch. Say which step was unclear, if
any. No screenshot or output containing credentials is needed.

This checks status/recovery/stop discovery on one known job. It does not establish
unaided usability for a population, immediate interruption of every process,
installation rollback, or production resource acceptance. No candidate was admitted
or activated by this experiment. Its transient workers are cleaned up by the run;
retained images, caches, evidence and backups stay in place. Do not use the private
runtime `remove` command against an invented path or delete images to undo this run.
