# Scanner correction preparation — November 3

The next runtime check will distinguish a failed AEEP bootstrap from a Cisco
scanner failure. The proposed bootstrap verifies the reviewed protocol file,
imports it under the parent image's Python, and retains only bounded failure
categories. The actual CLI scan follows only after bootstrap and containment
pass. Cisco's child keeps its existing private Python and reviewed image.

The host currently has **43.62 GiB usable free**, measured by Python and consistent
with `df`. This remains below the repository's 50 GiB reserve. The remaining full
tests and corrected-wheel installation have not started. Restore at least 52 GiB
usable space before source verification resumes; the 2 GiB headroom is for this
engineering work, not a product resource acceptance threshold. No cleanup ran.

## Prepared and checked

- `bootstrap-probe.py` is proposed contained code, not executed in a container.
  Seven in-memory controls check source drift, wrong import paths and sanitized
  import failures. They pass with explicitly labeled first-party substitutes.
- `package-check.py` adds an inert installed-wheel assertion for parent
  `python3` and child `/opt/aeep-scanner/bin/python`. Source command generation
  passes, and injecting the old launch makes this assertion fail. No wheel has
  been installed or tested by this check.
- All 32 existing dependency wheel hashes still match. The retained Cisco image
  remains `sha256:1cf3c4405db2f9b4721a35e10534f72a6b428fda49b3ee1114ef27d4f8a17eb4`.
  Docker inspection was metadata-only; no resource was started or changed.
- Product source remains `2df307d7be87d442e5795a0dc085282816944a41f64eb965a861780f629f2cd2`.
  Its five successful source gates and incomplete full run retain their original
  scope. These preparation checks do not close the remaining gates.

`review-draft.json` records the intended bounds and outstanding fingerprints.
It is **not executable or ready for approval**: the current-source full checks,
frozen source, corrected wheel and final execution definitions are still missing.
It does not grant authority or apply a budget amendment.

## Resume after usable capacity is restored

1. Check actual free space, Git edits and execution markers. Run the existing
   `../workflow-scanner-carrier-20261102/verify-source-resume.py` once, with
   `PYTHONPATH=src`, after at least 52 GiB is usable. It preserves the five
   unchanged source gates and uses post-teardown cleanup for passing fixtures.
2. After all gates pass, freeze that source and bind the built corrected wheel.
   Reuse the same 32 dependency wheels and retained image. Preserve unrelated CI
   edits and disclose their inclusion in source verification.
3. Finish the exact grouped driver/review. Derive the bootstrap Docker command
   from the corrected `ScanContainerExecutor.command`, replacing only its final
   protocol entrypoint arguments with the reviewed bootstrap program and input.
   Use existing authorization, operation reservations, receipts and verified
   container ownership/cleanup. The real scan uses the ordinary module CLI.
4. Preserve the original failed boundary charge on the existing canonical ledger.
   Prepare a finite amendment to its absolute scanner ceiling of three operations
   and 240 seconds, with zero models/cash and unchanged expiry. The fresh probe
   reserves 45 seconds; the scan reserves 165. The existing wrapper keeps its
   one-operation/30-second ceiling. Check current counters and amendment lineage
   before applying any amendment. No grant is recreated to reset usage.
5. Ask for approval of the completed artifact-bound execution review. Its two
   scanner calls and independent corrected-wheel check are not covered by the
   terminal `8f4ab6d3` attempt. Preserve that attempt's completed docs evidence;
   do not rerun successful scans or SDK checks for counts.

The earlier docs success retains its original input scope. A read-only hash
comparison found changes in two of its 72 inputs: `STATE.md` and `DECISIONS.md`.
The eventual grouped review must bind current documentation inputs and the same
cached offline tools. Current docs verification remains open; no checker was run
under an obsolete input review.

Both SkillsBench domains and the complete integration gate remain open.
Comparisons remain paused. No model, scanner, installation, service, image build,
release or deletion ran in this preparation. Current blocker: actual usable host
capacity, followed by exact approval once the corrected execution review exists.
