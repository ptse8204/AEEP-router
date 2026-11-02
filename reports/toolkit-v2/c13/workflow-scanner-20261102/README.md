# Ordinary workflow scanner connection

The workflow can select Cisco scanning for its captured candidate, charge the
scan separately from wrapper overhead, and require its canonical evidence before
execution or report export. Existing workflow v1 and accounting v1/v2 retain
their meanings. The new scan stage requires explicit accounting v3 authority.

The scanner uses the existing container executor, execution journal, operation
ledger and receipt store. It reuses retained image
`sha256:1cf3c4405db2f9b4721a35e10534f72a6b428fda49b3ee1114ef27d4f8a17eb4`.
No new scheduler, database implementation, registry service or image is introduced.
The preview lists all 92 retained scanner artifacts. This component runtime is
not an agent-comparison worker and provides no candidate-safety assurance.

## Implemented behavior

- `candidate --stage --manifest` captures filtered skill bytes and records the
  staged subject and setup costs without reading evaluation answers or creating
  a grant. Existing files and credential-state paths are rejected.
- `workflow define-scanner` stores an inert runtime definition.
- `workflow scan` previews permissions and the complete command. Explicit exact
  review and two existing scopes are required to charge wrapper and contained
  scanner work separately.
- The scanner validates its installed package against the reviewed wheel before
  importing Cisco. Finding identifiers, severity and analyzer failures are kept;
  snippets and diagnostic contents are excluded.
- `workflow run/report --scan-report` verifies the current candidate/source,
  runtime, settled operation, journal and receipt before attaching observations.
  Findings stay separate from task scores and usefulness.
- Cleanup checks ownership, exact image and immutable container identity.
  Uncertain cleanup blocks new dispatch; changing an operation ID cannot bypass
  it or refund consumed allowance. Images, volumes and unknown work are preserved.

## Verification status

All 13 source gates pass on unchanged source `0116d754`: 2,007 tests passed
with 21 skipped in both completed full runs, 82.54% coverage, both branch
floors, schemas and packaging. The [final record](verification-final/checks.json)
reuses the six unchanged successful original gates. Initial coverage hit 42
actual free-space guards. The next run passed every assertion but had two
pytest cleanup errors. Their complete logs remain. The final cleanup hook runs
after fixture teardown and preserves deliberate failures and skips; its controls
and the complete coverage run pass. No unsuccessful invocation is relabeled.
Only passing synthetic fixtures of the finished run were manually removed.
Allocated-byte and actual-recovery figures are separate in the cleanup record.
Numbered failed temporary roots later expired through pytest's normal retention;
their failure logs/metadata remain. No real benchmark evidence was stored there.

The [grouped review](operation-review.json), SHA-256 `8f4ab6d37cca76936274ac838394e15edd9391c5c76bae356ad5a98de01f135b`,
is prepared and passes inert verification. It is not approved or executed.
The actual module CLI previews both named three-task configurations and exposes
their real rights/runtime/assessment blockers. A pure scanner preview lists all
92 retained scanner artifacts. First-party driver controls check success and
independent failure handling. The native standard-library boundary and all
1,454 retained docs-tool files pass preparation checks. The previous
[actual scanner checks](../scanner-runtime-20261102/README.md) retain their
original source/scope. New current-source contained CLI execution is pending.

The package review is an inert draft even when space is short. Installation's
unchanged pre-effect guard and the driver require at least 50.72 GiB free
(50 GiB reserve plus closure and staging headroom). The package remains unstarted
without consuming its attempt while short; scanner/docs are independently eligible.
No older fixture, backup, image, volume or runtime cleanup is included.

The grouped check will use one fresh boundary probe and one actual scan through
the ordinary CLI, the changed wheel with 32 unchanged cached dependencies, and
cached offline documentation tools. It retains reusable runtimes. It runs no
models, benchmark tasks, services or new destinations and changes no Docker image.
Each component has its own attempt marker and receipts. Completed older SDK,
scanner/control and docs checks are not replayed.

## Remaining gates

Both named configurations select the three original SkillsBench tasks in their
domain. Previewing them or checking scanner applicability does not execute or
pass either workload journey. Task rights, exact runtimes, protected reference
and counterexample grading, real evaluator/worker composition and the remaining
upstream integrations are still open. Comparisons remain paused. Stack operation,
candidate usefulness, selection usefulness, resource acceptance and release are
separate gates.
