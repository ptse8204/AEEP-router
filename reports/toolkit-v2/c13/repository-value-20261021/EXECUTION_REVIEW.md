# Exact offline execution review

The bounded repository grader and separate selection evaluator are implemented
and committed as `9dabc5bd852853a49ab758eab68234ea6b64d17a`. This review validates their contained and installed
execution. It does not run a new model comparison or close C13.

Approval bundle SHA-256: `0d992ca99434868472bb47bced1785fadc92488e73ca1573c2bfc1d841730cc8`.

| Action | Exact permitted work | What it establishes |
| --- | --- | --- |
| Grader | 23 fresh offline contained observations; 25 canonical operations; at most 1240 reserved seconds on the existing grant | Current runtime can observe correct, unchanged and semantically wrong patches, with protected answers and cleanup receipts |
| Package | New wheel plus 32 exact cached dependency wheels; 18 sandboxed offline installed checks, then unchanged private runtime/scratch removal | The changed code works from the actual built wheel |
| Documentation | Cached pinned Lychee 0.24.2 under the verified sandbox; current 69 public documents; owned runtime removal | Offline documentation links on the current files |

No downloads, image pulls/builds, model proxy, model turns, credentials, cash,
host activation, publication or retained-image/volume/backup deletion. The
existing runtime image is
`sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7`.
The changed wheel is `681e820338033192ecce5830fc27016a557cccf186ca89637ecda3fba6388927`.

Each started component has one attempt. Unstarted independent components remain
covered by this exact approval if the dispatcher fails. Preserve all operations
and uncertain effects; never refund reservations or replay a started component.

## Completed source verification

Both full pytest runs pass 1619 tests, with 21 skips and 1 existing warning. Coverage
displays 82%; both critical branch gates pass. All 12 integrated checks pass,
including schemas, Ruff and wheel/sdist builds. Full-source mypy passes 167 files;
all 13 Node tests pass using existing dependencies, and the temporary link was
removed. The new focused suites contain 30 software checks on three development
source adaptations. They are not real candidate efficacy evidence.

The unchanged policy checker fails on `src/aeep/router.py:747`, where core imports
the Codex catalog validator directly. This existing layering issue is retained
as an open gate. Eight of nine supplemental checks pass; this review does not
waive that finding or establish release readiness.

## Why this approval is needed

The pasted continuation request excludes untrusted software execution, and
`docs/aeep-toolkit/CONTINUATION.md` requires applicable container-provisioning
authority. Earlier exact bundles are terminal and bind older code or artifacts.
Routine finite definition review remains delegated; no architecture or new
spending decision is requested. Actual approval must be recorded in
`bundle-operator-approval.json` with this raw digest and the human's words before
`run-bundle.py` can execute. No approval has been supplied or inferred.

## Remaining scientific work

The development examples are extracted AEEP maintenance contracts, including a
seeded fault and a no-change control. Independent real-task holdouts, reviewed
host mapping and live optional-capability/selection comparisons remain open.
The historical four-arm study remains INCONCLUSIVE. The synthetic ideal-policy
scorer example is not a live AEEP decision. Resource acceptance, the pending
human control exercise and release remain separate gates.
