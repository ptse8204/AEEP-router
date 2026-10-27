# Larger-repository bundle: known worker framing failure

Approved bundle `e6b1fb2c` ran once. The exact SciPy1.15.3 wheel verified on its
first fetch. The private image build passed, retaining
`sha256:2386ef223e39b5dc12e6d8cdbaa6ac9779753f13ee74dc51e8d207279edae91f`
at `aeep-toolkit-v2/repository-grader:py313-large-repositories-20261027`.
Measured image growth was72,906,965bytes; parent layers and execution configuration
were unchanged. The actual bundled license is retained separately from the
publisher's metadata license. No host package was installed.

Three fresh probes passed, including actual image dependencies, the SciPy sparse
calculation, and state separation. The fourth2.7MB transport probe failed. The
parent framing allowance was enlarged, but `container_worker.main` still read at
most2,000,001bytes and rejected input above2,000,000. This product defect prevented
the six repository tasks from starting. None was reproduced or adopted.

[Canonical reconciliation](initial-failure-reconciliation.json) reopens all four
receipts: three COMPLETED attempts and one FAILED attempt with complete terminal
evidence. All owned containers are absent and the unchanged canary was removed.
The report driver required COMPLETED for every call, so it initially described
the known terminal failure as uncertain. Reconciliation establishes no uncertain
attempt; it does not make the failed probe pass or permit its replay.

Eight operations were charged,including the fetch/build and runtime setup/analysis:
15.73691733321175seconds,zero models/cash. Counters are13189operations/3755turns/
119834.18554038461seconds/0.0cash. No charge was refunded. The51-case pool and90-case
gap remain unchanged. Every image,cache,receipt and failed record remains.

After reconciliation,the independently approved package/docs checks ran through
[a recorded first-party continuation](independent-control-review.json).
All19 installed checks passed on source1fde9517/wheel60466,and the exact69-document
offline docs snapshot passed. Both unchanged owned runtimes were removed. Later
state/guide updates are outside that completed docs snapshot. These successes do
not validate the failed worker framing or any benchmark/scientific gate.

The worker correction is prepared separately under `repository-worker-input-20261027`.
It passes a bounded operator-owned launch argument to the inner reader. Task data
cannot set it; old argv/default2MB semantics remain. Focused regressions exercise
both actual protocol readers. Full source verification is separate. This changes
product source and wheel,which the approved control-repair envelope explicitly
excludes. New executable verification therefore needs a new concrete approval;
no new download,installation dependency,image build or architecture choice is needed
for the retained grader image. Do not replay this terminal bundle.
