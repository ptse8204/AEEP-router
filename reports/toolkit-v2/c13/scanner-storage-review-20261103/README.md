# Scoped storage exception and scanner correction

This review would let pending engineering checks proceed with less free space.
The operator requested preparation of an exception; execution is not approved.
The normal 50 GiB policy and v1 serialized review digests remain unchanged.

The proposed floor is **42 GiB usable free**, with a **1 GiB net host-capacity
stop threshold** and an expiry within 24 hours. Checks run sequentially. The
largest observed fixture was about 0.6 GiB, and the private installation reserves
about 0.69 GiB including bootstrap headroom. These support a bounded attempt;
they do not establish resource qualification or a guaranteed continuous peak.
The controller checks real capacity every second during source verification.
Installation checks before effects and between steps, without interrupting a
running pip step. Other host activity counts against the stop threshold and is
not attributed to AEEP. Exact UTC expiry is in `storage-exception.json`.

## Proposed execution

1. Complete full pytest, branch coverage and the remaining current-source gates
   once. Reuse six successful checks on this exact source, including packaging.
   Remove only this run's passing fixtures after teardown; preserve failures and
   older roots.
2. Only after all 13 source gates pass, run one parent-Python bootstrap and one
   actual static scan through the ordinary CLI on retained Cisco image1cf3c440.
   The scan requires a successful probe and verified cleanup.
3. Independently check the corrected AEEP wheel with the same 32 cached
   dependencies in one retained private runtime. Run its sandbox and installed
   CLI/source/interpreter checks. No host activation.
4. Run cached offline docs verification on the bound current inputs. At most two
   attempts allow whitespace-only repairs with unchanged normalized input bytes.
   No source, tool, configuration or sandbox repair is authorized.

The original scanner grant keeps its failed operation and 0.5110439579002559 seconds.
Its prepared amendment raises the absolute ceiling to 3 operations/240 seconds,
with zero models/cash and unchanged expiry. Fresh calls reserve 45 and 165 seconds.
The original wrapper keeps 1 operation/30 seconds. Current-source scope amendments
reuse original grants and counters. These amendments are prepared, not applied.

No models, downloads, image builds/pulls, credentials, new services, payments,
release or deletion of existing resources. Only newly owned containers may be
stopped/removed after image, label and immutable-ID checks. All images, volumes,
backups and earlier runtimes stay. Settled component failure leaves independent
work eligible; accounting, ownership, source or capacity uncertainty stops
affected dispatch.

## Evidence and open gates

Source `1503d8d2` passes compile, schemas, policy, Ruff, mypy, packaging and 41 focused tests.
Three substituted driver controls check success, failed bootstrap and uncertain
cleanup without Docker or real amendments. An actual standard-library sandbox
probe verifies denied outside reads/writes and network. Full pytest/coverage,
actual scanner execution and corrected-wheel installation remain unstarted.

V2 binds the exception to one destination, filesystem device and wheel set.
Real capacity readings remain real. Explicit synthetic unit-test capacity cannot
substitute for host observations. Expiry does not prevent removal of an unchanged
owned runtime. Failed/interrupted setup keeps its journal and cannot replay.

The scanner dependency preview retains the earlier capacity declaration for
the already installed image. It is not a current host measurement; independent
dispatch guards use actual space. The earlier unapproved storage-exception
preparation remains at its original paths; this packet adds the Windows skip
for the unsupported private installer. No earlier execution approval transfers.

Both SkillsBench journeys and the all-integration gate remain open. Candidate
usefulness, selection usefulness, resource acceptance and release stay separate.
Comparisons remain paused.

## Resume

Approve the exact `operation-review.json` SHA-256, then record that approval in
`operator-approval.json`. Check component markers before invoking
`run-review.py --execute-approved REVIEW_SHA256 --component all` with
`PYTHONPATH=src`. Expiry or drift blocks dispatch. Never rerun a terminal
component under this one-attempt review. Continue only independently unstarted
components using the retained records.
