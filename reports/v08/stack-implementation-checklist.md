# Stack implementation, October 4–5, 2026

Base: `db0d854215e227ab003b584b18a6cc3408c2eb83`, clean main at inspection.
Authority: the operator's explicit implementation request and the September 25/27
finite test-definition delegation. No paid calls, new credential access,
assessment counter reset, publication or historical result changes.

| Increment | Implementation | Remaining gate |
|---|---|---|
| Architecture and code classification | ADR-011, contracts, this checklist | Recorded |
| Inert synthesis | Typed graphs, bounded deterministic beam, conservative compatibility, approved one-hop converters, policy aliases, evidence references, immutable successors | Bounded search does not establish global optimality; unsupported schema relationships remain unknown |
| Existing execution and authority | Pinned workflow nodes, actual-input prepared local decisions, explicit reviewed task-profile opt-in, zero-cash dispatch | Paid aggregate exposure and remote scoped execution belong to the later milestone |
| Durable recovery | SQLite migration 9, atomic run/attempt claims, fixed deadline, completed artifact digests, safe reserved retries, delegated continuation, reviewed successful-checkpoint recovery and successor amendment | Uncertain external effects must be reconciled through the existing attempt boundary; missing artifacts stop recovery |
| Configured discovery | One factory for CLI/API sources: ARD, fixture, MCP, Docker catalog, Smithery, local package; legacy compatibility re-exports | No automatic code loading, intake or admission |
| Provider setup | Reviewed source-pinned HTTPS/local/host adapters, handoffs, explicit secret references, sanitized expiring observations and check intents | Provider-specific installation/provisioning is unsupported unless supplied through an existing reviewed host lifecycle |
| Agent/operator interfaces | `StackService`, `StackRuntime`, `aeep stack`, shared prep schemas, opt-in scoped run tool | Native task-scope v1 boundaries retained |
| Offline generality | Media edit timeline, grouped data report, referenced fixture facts; local/host/converter/missing-provider/setup-required cases | Full validation results recorded separately below; fixtures are not real provider outputs |
| Actual provider readiness | Existing Hugging Face and Figma authentication checks; exact local Python version checks | **Incomplete:** new operator-completed sign-in journey, credential-bound metered billing readiness and standalone provider integration evidence |
| Paid execution and value study | Deferred as specified in step 7 | Separate authority, adapter boundary evidence, exact live-task limits, controlled three-way comparison |
| Optional imports and historical archive | Classification recorded; legacy API isolated behind compatibility imports | Package splitting and archive movement deferred; no deletion performed |

## Exact implementation review

The finite test amendment comprises `tests/test_stack_planning.py` and
`tests/test_stack_setup_discovery.py`, plus additive tool-inventory expectations
in existing CLI/MCP/import tests and the current database-schema assertion.
These tests exercise inert planning, domain results, unknown compatibility,
converter accounting, source drift, reviewed setup, cancellation, missing
credentials, billing unknowns, duplicate/concurrent claims, retained artifacts,
retry limits, predecessor consumption, host delegation and scoped model ceilings.
The native task-profile test patches the launcher only within a temporary test;
it is software evidence, not a new native containment qualification.

Focused checks found a schema-migration fixture conflict. The initial full run
found outdated tool expectations, stale generated schemas and profile exposure
incompatibility. Those were repaired. That run overlapped source edits, so its
source-bound campaign failures do not validate a fixed revision. The initial log
is retained. Later validation runs freeze implementation source. A separate active verification-lock review records the exact before/after
digest for the additive imported-tool expectation; historical run evidence and
qualification thresholds remain untouched.

Read [STACK_PLANNING.md](../../docs/STACK_PLANNING.md) for commands, persistence,
compatibility and recovery rules. The operator retains ordinary exact review;
there is no new approval or accounting database. Model arguments cannot select
setup adapters, review definitions, approve reconciliation or raise task ceilings.

## Validation record

[The final validation summary](stack-validation-20261005/summary.md) links command
arrays, exit codes, elapsed times, retained failures and coverage output. Both the
plain and branch-coverage pytest runs passed 1,266 tests with 21 skipped. Overall
coverage is 82%; critical and assessment branch gates passed. Compile, schemas,
lint, types, policy, compatibility checks, strict router verification and package
builds passed. A preceding frozen run had one outdated verification-lock digest;
a subsequent run was deliberately interrupted after 821 passes before extending
converter search. Both logs remain available.

[Provider observations](stack-readiness/host-connections.json) omit account
identifiers and credentials. The first local observation is preserved; a second
explicit one-call review and result cover the adapter-revision pinning repair.
Readiness was current at each check and expires; archived observations do not
represent indefinite current access. The source-bound check does not establish
qualification, admission or payment authority.

## Storage and resources

The initial storage check found about 133 GiB free. Before final verification,
about 118 GiB remained, above the 50 GiB reserve. No dependencies, images or
containers were installed, built, pulled or removed. Test databases and local
provider-package verification use existing temporary/example paths. Both the wheel and source archive built without installing dependencies. Final
output paths and hashes are in `stack-validation-20261005/packaging-final.json`.
Persistent data and unrelated resources are retained.
