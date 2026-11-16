# Optional LibCST rerun on CANopen and Xsdata

Both pairs completed on GPT-6.1 Sol at medium reasoning with matched
300-second limits. The [review](libcst-direct-review.json) bound the
original public inputs, protected grader, arm order and retained worker
images for each task.

| Task | Control / treatment score | Δ input tokens | Δ output tokens | Agent time control / treatment |
| --- | ---: | ---: | ---: | ---: |
| CANopen 613 | 0/1 / 0/1 | +24,682 | +316 | 84.93 s / 91.10 s |
| Xsdata 1126 | 0/1 / 0/1 | −2,161 | −298 | 98.26 s / 92.59 s |

Deltas are treatment minus control. Agent time excludes protected
grading. The [canonical result](libcst-direct-result.json) includes
per-arm times, raw token categories, all required test statuses and
receipt references. All four pytest runs exited 1.

- Both CANopen arms passed 6 of 8 required tests. The PDO indexing and
  iteration tests `TestPDO::test_pdo_getitem` and
  `TestPDO::test_pdo_iterate` failed in both.
- Both Xsdata arms passed 28 of 29 required tests. The sole failure was
  `UnnestInnerClassesTests::test_update_types` in both.

Across all four turns the observers recorded zero covered direct
imports, parses, transformations or reviewed helper calls. Candidate
instruction loading was also unverified. These runs demonstrate no
score improvement from making LibCST available. They leave open
whether using LibCST would have improved these tasks.

## Measurement coverage

The host observes successful direct Python commands through paired Codex
App Server start and terminal events. It recognizes an isolated interpreter
with a fixed read-only package root and a bounded inline program, including
ordinary `import libcst`, `parse_module`, a built-in CST visitor and the
upstream rename codemod. A successful comparison of the original and
transformed trees can verify a changed or equal preview. It does not
measure whether the code was applied to the submitted patch. Named helper
invocations and candidate instruction loading are separate measurements.

Both arms received identical optional syntax guidance and used retained
worker images. Control kept its ordinary Python and editing tools.
Treatment retained optional LibCST 1.8.6 and the reviewed read-only helper.
The collector recorded only classifications, counters and digests. It
bound those records to the exact runtime, attempt, thread, turn and paired
native events through the canonical execution journal. It retained no
command text or model-written evidence claims.

The [offline evidence](libcst-direct-offline-evidence.json) shows actual
direct import, parse, rename, no-change transformation and workspace-file
read. The treatment package bound 302 read-only files. Controls rejected
a missing package despite a writable shadow module, invalid syntax, shell
composition, changed identity and receipt tampering. The first offline
preflight stopped before creating any container because it expected
the wrong spelling of the Docker capability flag. The corrected check
kept the original boundary.

Standalone scripts, other interpreter or shell forms, arbitrary custom
transformer code and command patterns outside the recognized subset
remain unobserved. Zero observed calls means zero within that subset.

The [readback audit](libcst-direct-audit.json) reconciled all four
canonical receipts, both observers, the protected grades and token
capture. This rerun settled 21 operations and four model turns in
401.90 summed operation seconds with $0 cash. The proxy returned to
its exact stopped state. Historical reservations remain and there are
no new unresolved reservations.

The experiment scripts compiled. A direct Ruff check of the report
directory flagged nine import and style findings in the executed
scripts. This directory is outside the repository's standard Ruff
scope. The reviewed script bytes and their hashes are preserved.
