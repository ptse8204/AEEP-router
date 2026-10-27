# Six-suite reproduction results — October 27

Approved review `c81557a2` completed once on unchanged product source `4cb0bf74`.
Three workloads reproduced and three remain excluded. This prepares task graders;
it is not a model comparison, qualification or evidence of capability value.

| Workload | Reference observation | Counterexample | Curation result |
| --- | --- | --- | --- |
| MCP Python SDK222 | Collection error, exit2; 55 required identities absent | Unstarted | Excluded |
| MCP Python SDK384 audit | Collection error, exit2; five required identities absent | Unstarted | Excluded |
| Goodconf51 audit | All22 required identities passed | Rejected | Eligible |
| Twyn317 | Collection error, exit2; 43 required identities absent | Unstarted | Excluded |
| Dishka512 | All15 required identities passed | Rejected | Eligible |
| Prometheus Python1134 audit | All30 required identities passed | Rejected | Eligible |

The existing observer retained statuses and exit codes, but no exception causes.
No missing package or code defect can be inferred from these collection errors.
Earlier failures remain failed; changed runtime evidence does not repair them.

[The canonical audit](runtime-execution/completion-audit.json) reopened all12
physical receipts and completed attempts, checked their identities and confirmed
owned-container removal. [Consolidation](consolidate-results.py) also reopened the
build and child ledgers: all15 operations completed and35.61532362597063
operation-seconds were charged. Model turns and cash did not change. The current
grant is13134 operations,3755 turns,119716.31834351085 seconds and0.0 cash, under
the existing expiry-only amendment. No allowance is refunded or reusable.

The retained image is
`aeep-toolkit-v2/repository-grader:py313-cached-suites-20261027`,
`sha256:f60342e9c6a50933353ebea047b89935c75579541cf628f4fe4d15a1c0515e93`.
It grew8,527,902 bytes from retained parent `b0eb4add`; both remain available.
Three fresh containment/state/runtime probes passed. Only the unchanged owned
canary and attempt-owned containers were removed. All old images and volumes
remain untouched.

[The provisional pool](provisional-pool.json) now contains42 snapshots across27
repository groups and2613 required identities:16 single-file repairs,18 multi-file
repairs and8 contract audits. Reaching the unchanged balanced141-case plan still
requires31 single-file,29 multi-file and39 audit cases,99 total. All earlier
source/runtime bindings are preserved. No stage is frozen and no case is admitted.

The next step is a separate bounded diagnostic for the four failed collections
(including the preceding CanvasAPI case). It must capture only sanitized exception
categories and reviewed module identifiers, preserve every failed result, and use
new exact execution authority. It must not replay a terminal review or install
speculative dependency fixes. Source, package and full test runs are unchanged;
no broad rerun was needed. Infrastructure resource acceptance remains separate.
