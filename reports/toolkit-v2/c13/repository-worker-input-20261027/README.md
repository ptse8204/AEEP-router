# Correct the inner worker input limit

The larger repository path needs both protocol readers to accept the same
reviewed frame. The host wrapper had been updated,but the inner worker still
rejected anything over2MB. Source `374579f1` passes the operator's bound through
launch argv and validates it before reading. Default launches retain their old
argv and2MB limit. Task data cannot raise the allowance.

[The preceding approved bundle](../repository-large-archives-20261027/RESULTS.md)
built retained image2386 and passed three probes before the2.7MB probe exposed
this defect. All four attempts are terminal and all owned containers are absent.
Eight operations/15.73691733321175seconds stay charged,with zero models/cash.
The independently approved package19 checks and exact offline docs snapshot
passed on the preceding source. No repository task ran.

## Verification

The focused regression sends2.7MB through both actual protocol readers using a
local Docker protocol stand-in; it proves framing,not OS isolation. Worker tests
also verify default rejection and invalid-launch denial before reading input.
[The frozen legacy recipe](legacy-compatibility.json) reconstructs identically.
[Collector fixtures](terminal-control-check.json) use private copies of real
terminal evidence and replace all dispatch: COMPLETED succeeds,known FAILED
stays failed,and nonterminal/uncertain cleanup stops the batch.

[All13 source checks](validation/checks.json) passed on source374579f1 and commit
1f7d27d:1,735 tests in each full run,21 skips,82%coverage and both branch gates.
Compilation,schemas,integration checks,Ruff,mypy and wheel/sdist builds passed.
Session38330 is terminal and was not repeated. [The built artifacts](build-artifacts.json)
retain exact hashes. The corrected wheel's SHA-256 is `9b00add749cf7b8c5486bc878838fcdc28c517dc02a3b6d662ed477dd579ef1d`.
No corrected-wheel installation or new container invocation has run.

## Next execution scope

[The prepared combined review](approval-bundle.json) binds the exact source,wheel,
runtime and documentation. It is not yet approved or executed. Reuse image
`sha256:2386ef223e39b5dc12e6d8cdbaa6ac9779753f13ee74dc51e8d207279edae91f`.
No dependency,download,image build or service is needed. The same four fresh
probes and twelve unchanged variants cover Cyclopts609/633/701,NetworkX7804/8055
andIsort2491. The probe/test/reference bytes,required identities and scientific
thresholds stay fixed. The new source needs its own fresh worker evidence.

The proposed cumulative ceiling is20 calls/24 existing-grant operations/1,000
reserved seconds,including four bounded same-software diagnostic calls and a
second setup/analysis phase for recorded first-party controls. Unknown attempts
cannot be replayed; all charges and images remain. The current corrected wheel
plus32 cached dependencies needs19 private installed checks,including an actual
installed-worker positive/default-denial framing exercise. Cached offline docs
verification is separate. Zero models,cash,credentials,activation or release.

The preceding approval explicitly excludes changed product source/wheel from its
control-repair allowance. The exact corrected executable therefore needs approval;
no architecture or budget decision is open. The historical51-case pool and90-case
gap remain. Grader reproduction will not establish comparative usefulness or
selection quality. Qualification,value,selection,resource acceptance,unaided human
controls and release remain open.

[The next metadata queue](next-multifile-metadata-queue.json) identifies14 potential
multi-file tasks across11 repositories from cached metadata only. Prior exclusions
must be reviewed before source collection. No case is adopted and no new archive
was fetched by that preparation.
