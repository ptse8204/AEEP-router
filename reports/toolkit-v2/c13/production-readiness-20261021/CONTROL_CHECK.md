# C13 control check: exactly what to do

This is a short, assisted control walkthrough for the completed Toolkit journey.
You will read supported controls and tell us what you would do. You do not need
to reinstall, start a model, cancel a completed job or remove anything. The earlier
answers and scope clarification stay recorded; this repeat is scored as helped.

## 1. Open the actual state record

Open [the completed capture audit](../../c07/capture-explicit-profile-20261021/completion-audit.json).
Find `proxy.running`, each image's `referencing_containers`, and the report/trial
identifiers. This is the last recorded state, not a live health check. The capture
journey enabled no persistent host connection, automatic candidate use or native
project activation. Its private installation runtime was already removed.

## 2. Read the two supported control interfaces

In your Mac Terminal, copy these three commands, one at a time:

```bash
cd /Users/edwintse/Documents/aeep-toolkit-v2
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m aeep.cli assess --help
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m aeep_toolkit.cli remove --help
```

These only print help. Find `cancel` and `status` in the first output, and
`--installation` and `--reviewed-digest` in the second. The exact commands were
checked with network, writes and unrelated home access denied. No assessment,
installation or model ran. If they fail on your Terminal, paste the error instead
of installing anything or changing your configuration.

## 3. Understand what the controls do

For a future active assessment, the existing operator control is `assess cancel`.
It marks that one job cancelled; scheduling checks the state before the next
trial. It does not forcibly terminate an in-flight child or prove external effects
were rolled back. Preserve the job/attempt/receipt/usage, inspect `assess status`,
and reconcile uncertain effects before any further run. Ctrl-C can interrupt the
foreground coordinator; it is also not proof of cleanup. There is no general
Toolkit pause/resume command that safely resets or replays a started assessment.

These are reference command shapes for a future reviewed active job. They are
not commands to execute during this check. Obtain the manifest, assessment directory
and exact active job ID from that run's reviewed record:

```text
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m aeep.cli assess --manifest REVIEWED_MANIFEST --directory REVIEWED_ASSESSMENT_DIRECTORY cancel ACTIVE_ASSESSMENT_ID
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m aeep.cli assess --manifest REVIEWED_MANIFEST --directory REVIEWED_ASSESSMENT_DIRECTORY status ACTIVE_ASSESSMENT_ID
```

For a future private installation, stop its owned processes first and use `remove`
with the exact installation document and its review digest. The document is the
saved `install-plan` output containing `review_sha256` and `installation`, not an
arbitrary package review or a raw internal installation object:

```text
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m aeep_toolkit.cli remove --installation EXACT_INSTALL_PLAN_OUTPUT_JSON --reviewed-digest EXACT_REVIEW_SHA256
```

Removal checks the exact owned runtime tree. Edits, additions or an incomplete
state block removal and preserve contents. Keep its journal/lock and retained
assessment evidence. Do not replace this with manual deletion, image pruning or
removing another environment. This journey has no current private runtime to
remove and no project activation to undo. See the unchanged
[installation contract](../../../../docs/aeep-toolkit/INSTALLATION_DESIGN.md#implemented-private-wheel-runtime).

## 4. Reply with your actual observations

Use your own words; a short response is enough:

- Did both help commands work, and could you find the named controls?
- What, if anything, needs stopping or undoing in the recorded completed journey?
- If a future job is active, what would you use to stop new dispatch, and what
  would you still need to inspect before another run?
- Which inputs does private removal need, and what would you do if its tree
  changed or removal was refused?

You can say “unclear” or paste an error. Your response is the remaining human
control evidence. These instructions and command checks cannot supply it. We will
record the help provided and any remaining product problem without overwriting
the earlier responses or claiming unaided/population-wide usability.
