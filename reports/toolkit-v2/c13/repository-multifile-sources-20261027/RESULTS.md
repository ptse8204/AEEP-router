# Four-workload results

The approved `ad0adfcf` bundle ran once. Canopen 613 reproduced as a multi-file
repair. WebAuthn 241 and both Xsdata tasks remain excluded under these definitions.
The runtime pipeline and exact offline documentation snapshot completed; that
pipeline result does not mean all four subjects passed.

| Subject | Observed result | Disposition |
|---|---|---|
| Canopen 613 | Reference passed; original and both partial repairs rejected | Eligible provisional snapshot |
| WebAuthn 241 | Reference passed; original rejected; first partial also passed | Old multi-file definition rejected |
| Xsdata 1126 | Reference exited 4 before collection: `--benchmark-skip` unrecognized | Excluded; remaining variants unstarted |
| Xsdata 1132 | Same configuration failure | Excluded; remaining variants unstarted |

All four fresh probes passed, including dependency/source-copy identity, boundary,
state separation and large-input framing. The retained output image is
`sha256:9f473c493b7af1854922807d2acbdcbe3b955313dc57f203e6f73c9c50f9ea85`, tag
`aeep-toolkit-v2/repository-grader:py313-multifile-20261027`. It preserves parent
`2386ef22` and adds three layers totaling 11,649,750 bytes. Eight exact cached
wheels were installed privately; unchanged untokenize source and publisher
metadata were copied without running setup.py. All images remain.

[The canonical audit](final-accounting-audit.json) reopened 13 completed attempts
and physical receipts, plus all 16 operations. They charged
35.3654196257703 operation seconds, zero model turns and zero cash. Current grant:
13,222 operations, 3,755 turns, 119,916.5088296351 seconds and 0.0 cash. All owned
containers and the unchanged canary are absent. Four extra diagnostic calls were
unused; this terminal approval cannot be replayed or transferred.

## Task-contract correction

The WebAuthn issue requests a SafetyNet `basicIntegrity` change. The full published
patch also removes an authentication-response field, which the issue does not
require. The passing partial preserves that API and is legitimate for the issue.
Do not add an assertion forcing unrelated cleanup to make the full patch necessary.
A new single-file task will restrict edits to SafetyNet, restore both original
`user_verified` assertions and retain all 11 required identities. The old result
stays rejected as a multi-file task.

Xsdata's source config requests `--benchmark-skip`. The image already contains
pytest-benchmark 5.1.0, but the explicit plugin list omitted it while plugin
autoloading was disabled. Prepare a fresh check with `pytest_benchmark.plugin`;
keep the project option, source, reference, protected tests and required identities.
No new install or image is needed. These changed task/plugin payloads require a
new exact execution review under the operator's untrusted-execution boundary.

## Scientific status

[The provisional pool](provisional-pool.json) now contains 57 snapshots across
36 repositories and 3,067 required identities: 22 single-file, 20 multi-file and
15 audit tasks. The balanced 141-case design still needs 84 cases (25/27/32).
Historical source/runtime bindings remain separate. Stages are not frozen and no
model qualification, comparative usefulness, selection, resource, human-control
or release gate closes here. Current source `374579f1` and wheel `9b00add7` retain
their completed source and installation checks; neither was repeated.
