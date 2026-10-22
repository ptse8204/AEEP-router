# Real repository grader compatibility check

This check determines whether AEEP can reuse upstream repository tests and grading
on the existing offline runtime before committing model turns to those workloads.
It is for the implementation coordinator. Execution is pending exact approval;
the preparation checks passed without running external source.

The reviewed task is `delgan__loguru-1451`, based on Loguru commit
`2abeb0fa6d7be4b0455c6e0b580b1e9dab19005e`. The source archive and license are
pinned in [the source record](../repository-cohort-20261022/development-source-review.json).
This inspected task and `pgmpy__pgmpy-3137` are excluded from future holdouts.

The six fresh containers check:

- Host-canary denial, read-only root, denied network and nonroot execution.
- Two-container state freshness.
- The unchanged Loguru tree with the upstream test patch: two expected bug-test
  failures and 22 preservation passes.
- The published repair: all 24 required test identities pass.
- The published repair with an added uppercase-output regression: the two bug
  tests still pass but at least one preservation test fails.

The last three expectations are unexecuted predictions. Their actual results will
be recorded, including failures. The grader uses exact function and enum bodies
from the MIT-licensed SWE-rebench harness fork at
`980d0cca8aa4e73f1d9f894e906370bef8c4de8a`. The bodies and license are retained
here. This is reuse of its pytest parser and resolution rules, not a claim that
the full upstream harness or image has passed.

Seven exact cached pure-Python wheels load privately through zipimport. Nothing
is installed on the host. The adapted runtime uses pytest 8.3.5 instead of the
task's suggested 8.4.1 dev extra, keeping all wheel and repository bytes inside
the existing container transport without Pygments. Official-image equivalence
and broader repository compatibility remain unknown.

[The operation review](operation-review.json) binds the source digest, runner,
payload hashes, exact wheels, existing image, grant and finite scope. Its raw
SHA-256 is `56ca1751c4774dbaa4b4b10d511727220bb93bef5d2fe2626b2329d32c3c64a5`.
The ceiling is eight canonical operations and 360 reserved seconds, with zero
model turns and zero cash. It permits no downloads, image builds/pulls, credentials,
activation, release or retained-resource deletion. Existing attempt-owned
containers and the unchanged synthetic canary are the only execution cleanup.

`run.py` requires a separate actual operator approval record and an unconsumed
exclusive start marker. It uses existing `AssessmentService` authorization,
atomic reservations, `Router`, `ContainerExecutor`, receipt storage and the same
canonical grant. All previous usage remains. It stops on source or payload drift,
failed containment, unexpected test identities, missing tests or cleanup failure.
There is no automatic retry after the execution marker.

[Preparation checks](preparation-checks.json) verify source hashes, existing schema
bindings, all three payloads, seven wheel hashes, the actual transport size,
archive rejection cases and unchanged upstream function bodies. They do not
execute Loguru, pytest, freezegun or upstream grading code. The earlier inert
preparation failure is preserved: Git discovered the enclosing checkout and
skipped nested fixture patches. Preparation now blocks that discovery and checks
the resulting test and repair content explicitly.

After approval, the coordinator records the verbatim response and review digest
in `operator-approval.json`, then runs the driver once from the implementation
checkout:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  reports/toolkit-v2/c13/rebench-grader-20261022/run.py \
  56ca1751c4774dbaa4b4b10d511727220bb93bef5d2fe2626b2329d32c3c64a5
```

The driver writes `execution-result.json` and `operation-ledger.json`, with
canonical per-call receipt references and physical container cleanup checks.
Until those files exist, this is prepared, not passed. Standard upstream log
parsing does not prove resistance to adversarial output forgery or test gaps.
One public development issue cannot qualify a candidate, demonstrate its value,
establish selection quality or pass resource acceptance. The remaining engineering
sequence is in [the workload plan](../repository-cohort-20261022/WORKLOAD_PLAN.md).
