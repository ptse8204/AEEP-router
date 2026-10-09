# Private package installation review

Install the built AEEP wheel and its 32 pinned dependencies only into the new
private directory in `review.json`. The 33 wheel hashes, runtime interpreter,
source revision, licenses, permissions and removal behavior are in
`installation.json`; `operator-plan.json` wraps the same plan for the CLI.
No installation has run. The earlier D19 approval covered a different 24-wheel
agent-skill-eval environment.

This is an offline installation and removal test, not production activation.
The artifact collection is 14,834,507 bytes. The lower disk reservation is
729,604,577 bytes; observed free space was 97,917,427,712 bytes. Keep the 50 GiB
reserve and recheck it at execution. Runtime memory is unknown; the proposed
policy explicitly acknowledges it without reporting zero or a guessed amount.

Run the installed CLI's help, candidate inspection, metadata preview and synthetic
report commands in a fresh temporary HOME with Python isolated mode and bytecode
writes disabled. Do not activate the environment, contact a provider, launch a
host, read credentials or change user configuration. Scripted and managed worker
execution still require their reviewed checkout assets and separate trial scope.
The dependency versions match the current regression environment; this inspection
is not a vulnerability audit or production security qualification.

After checks, use the existing installer snapshot to verify the whole runtime is
unchanged before removal. A changed tree must be preserved. Keep the sibling
journal and exact command/results record. The previous artifact collection and
agent-skill-eval runtime remain untouched.

`run_review.py` is the prepared test driver. With no execution flag it checks
only the pinned review and wheel hashes. Use the reviewed Framework Python:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B \
  reports/toolkit-v2/c06/package-installation/review/run_review.py
```

After the operator answers the pending installation review, the driver accepts
`--execute-reviewed-digest` with the exact digest in `review.json`. This flag is
not authorization by itself. It checks installed help, candidate inspection,
metadata preview and all three report formats, then verifies that the installed
scripted backend reports its checkout requirement. Removal uses the existing
whole-tree conflict check. An interrupted or changed installation is preserved.
The driver does not test the later sharing-preview feature because this reviewed
wheel is deliberately still bound to source `5386064`.
