# Protocol-neutral worker implementation: validation checkpoint

This checkpoint records implementation progress on 21 September 2026. It is not
a completed assessment-product release. The full requirement ledger is in
[plan-coverage.md](plan-coverage.md), and the repository policy is in
[ASSESSMENT_TESTING.md](../../docs/ASSESSMENT_TESTING.md).

## Implemented and checked

- Provider-neutral capabilities, handles, events and evidence; explicit adapter
  registration; compatibility with existing executor and Router entry points.
- Codex Exec JSONL normalization, experimental App Server events, MCP result
  envelopes, cancellation-request semantics and unknown-capability rejection.
- Durable sanitized event journals, cumulative usage snapshots, conflicting
  event rejection and explicit receipt/admission/attempt lineage.
- Pinned managed-worker launch profiles with private writable state, bounded
  resources and no host bind mounts; verified launcher inputs and packaged assets.
- Immutable scope amendments and atomic bundle review using the original grant
  counters; no new allowance on an environment or definition change.
- Bounded structural applicability extraction, independent literal grader
  fixtures, stored grader-validation evidence and admission checks for that
  evidence and current worker conformance.
- Root agent instructions, the canonical testing runbook, policy/import checks,
  test markers, critical branch gates, schemas and documentation links.

## Validation evidence

| Check | Result |
| --- | --- |
| Full branch-coverage pytest run | 789 passed, 6 skipped; 272.82 seconds |
| Ordinary pytest run | 789 passed, 6 skipped; 193.07 seconds |
| Overall coverage | 81.52%; 80% floor retained |
| App Server critical branch gate | 211/234, 90.17% |
| Boundary verification | 15/16, 93.75% |
| Production worker binding | 8/8, 100% |
| Grant amendment transaction | 17/18, 94.44% |
| Capability eligibility | 2/2, 100% |
| Applicability, authorization, reservation, completion | 100% of gated branches |
| Atomic admission | 23/24, 95.83% |
| Existing critical gates | Passed |
| Real container tests | Five passed, including worker death, cleanup and the managed transport fixture |
| Node integration | 13 passed |
| Compilation, schemas, Ruff, mypy, policy checker | Passed; mypy checked 114 source files |
| Existing CI proof commands and provider verification | Passed |
| Legacy router verifier | Core, OpenAI and marketplace-contract profiles passed; marketplace-live disabled |
| Wheel and sdist | Built; managed-worker assets present in wheel |
| Assessment-product verifier | Offline and native containment checks passed; live host verification and release readiness remain false |

The generated [product-verifier record](protocol-neutral-workers-product.json)
binds its checks to the current source digest. It was run with `--real-container`
and without `--release-checks`; its compatibility field therefore remains false.
The individual compatibility commands are recorded above. This distinction does
not change the outstanding implementation and live gates.

The managed transport fixture is a local test executable, not a Codex model.
Native-container success does not establish hosted-tool permissions, credential
protection or model-service egress isolation. Historical reports were preserved;
new adapter tests reside in the assessment test file so historical test-file
digests remain valid.

## Remaining work and blockers

| Area | Remaining work |
| --- | --- |
| Recipe implementation | General reviewed executable generators, graders and adapters must enter the same controlled campaign pipeline; the declarative record-template path is available |
| Worker lifecycle | Fresh/reused worker conditions, fresh case workspaces and holdout resets need complete campaign integration |
| Worker containment | Provision pinned Codex images; enforce and verify credential isolation, effective hosted-tool policy and separate model-service versus candidate network permissions |
| Spreadsheets | Provision and verify Linux dependencies for the complete plugin; installed Node, Python and skia-canvas binaries are Mach-O arm64 |
| Adapter capabilities | Exec skill invocation, streamed events and supported actual identity observations remain unavailable; App Server remains experimental |
| Planning and intake | Finish isolated worker planning, complete reviewed plugin mappings and actionable setup diagnostics |
| Evidence and production use | Complete workflow-level canonical lineage, source-bound controlled-fixture release evidence and verified production worker use |
| Live acceptance | Run the whole-plugin Spreadsheets screening first, then the three-family/new-recipe journey within available authorization; no live model assessment was started in this implementation checkpoint |

The live grant remains unchanged: 302 operations, two reserved turn allowances,
93.31732538260985 seconds charged and zero cash. It has 298 turn allowances and
about 3,506.683 seconds remaining. Four full two-agent-arm campaigns require at
least 1,128 turns before overhead and therefore cannot fit this grant. The
thresholds, counters and disclosure restrictions have not been relaxed.

Implementation completion, host/container conformance, live product acceptance,
controlled-fixture release evidence, demonstrated savings and adapter production
support remain separate decisions. Passing these checks does not close the
unfinished rows above.
