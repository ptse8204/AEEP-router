# Execution boundary and recipe completion status

The implementation is not a completed live product release. The source-bound
release verifier keeps its gates separate; a successful local fixture cannot
establish plugin savings or production support.

## Implemented in this continuation

- Reviewed executable recipes use contained generators, graders and independent
  references through BenchmarkRunner. Runtime drift is rejected before generation,
  and generated case sets belong to one reviewed plan.
- Native trial mounts expose the current fixture only. Managed workers bind the
  full immutable image, binary, resource limits and reviewed security profiles.
- Exec streams bounded JSONL into durable canonical evidence. Failed event writes
  stop execution, and incomplete streams retain observed usage.
- Shared invocation checks reach managed adapters immediately before dispatch.
  App Server accepts a conformance reference only through that internal path;
  permission acknowledgements and inventory matches alone remain insufficient.
- Grant creation is atomic. Clock rollback cannot discard an attempt transition.
  Source fingerprints ignore generated package metadata and include package config.
- A source-bound controlled fixture exercises admission, actual use, revocation,
  stale-decision rejection and baseline recovery. The release verifier checks its
  records and reports adapter production support separately.

## Concrete environment evidence

| Check | Evidence | Limit |
| --- | --- | --- |
| Linux Spreadsheets dependencies | `spreadsheets-linux-dependencies.json`: CSV import and XLSX export; `spreadsheets-worker-review.json`: actual skill discovery, fallback runtime, CSV access and authoring helper | Local setup is verified for the frozen review image; model-driven use and other authoring features remain unverified |
| Plain versus plugin setup | `plain-worker-review.json` advertises no enabled skills; the candidate advertises only Spreadsheets | Advertised skill enablement is not verified tool availability; neither image is approved for model execution |
| Fresh Linux Codex workers | `managed-worker-profile-probe.json`: two successful no-model sandbox runs with private writable workspaces | The policy is an unapproved review template, not full conformance |
| Credential canary | `linux-sandbox-nested-probe.json`: synthetic credential path denied in the local namespace probe | Requires the complete probe set and effective policy verification after worker login |
| Controlled admission lifecycle | `.aeep/controlled-release-v8/evidence.json` and its local authority database | Deliberately delayed reference; no real plugin benefit claim |

## Remaining work and blockers

| Area | What remains | Why it cannot be treated as complete |
| --- | --- | --- |
| Worker authorization | Review exact images, profiles, dependency mappings and apply an amendment to the existing grant | Earlier approval binds the earlier definitions; amendments must retain the same counters |
| Model-service network | Provision reviewed egress enforcement separately from the command sandbox | A Docker network ID or disabled command network alone does not prove the full network boundary |
| Worker authentication | Use Codex-managed sign-in in each protected worker volume | No desktop authentication state may be copied or inspected |
| Conformance | Run all harmless probes, validate effective post-login policy, inventory, identity and complete events | Current local probes establish individual observations only |
| Exec identity and skills | Obtain supported identity observations and verify explicit skill execution for this adapter/version | Exec currently reports identity as unknown and rejects unsupported invocation modes |
| Reused workers | Implement and verify fresh conversations, private case state and holdout reset for a persistent managed process | The comparison choice remains unavailable. `codex-process-schema-review.json` records that the installed termination endpoint covers client-created sessions, not all agent-launched processes |
| Spreadsheets workflow | Review the concrete local-file mapping and images in `spreadsheets-worker-review/README.md`; verify actual model-driven skill use | The runtime fallback and authoring helper now work in the candidate image. Connected Excel and untested authoring features remain outside this evidence |
| Live product acceptance | Three shipped families, one reviewed new recipe, model-driven task calls and scoped use or justified rejection | No new live assessment model turn has started |
| Allowance | Re-read the existing grant before any execution | It has 298 reserved-turn allowances and about 3,506.7 seconds left; four full two-arm campaigns require at least 1,128 turns before overhead |
| Production support and savings | Validate supported-adapter operation and measure real candidate outcomes separately | App Server remains experimental; no real plugin benefit has been demonstrated |

The complete requirement map remains in [plan-coverage.md](plan-coverage.md).
Final validation is recorded in [execution-boundary-validation.json](execution-boundary-validation.json),
[execution-boundary-checks.json](execution-boundary-checks.json), and the
`execution-boundary-logs/` directory. The combined verifier passed offline
assessment checks, real containment, controlled-fixture validation and all
compatibility checks. The full suite passed 810 tests, with three skips and five
container tests run separately; all five passed. Overall branch-mode coverage is
81.66%, above the unchanged 80% floor. Both critical coverage gates, CI proofs,
13 Node integration tests and wheel/sdist builds passed.

Source digest: `33ee4c0a3a29491a3318e9521c507a9bdbc108e230abc9eda95f004b8f3fe8eb`.
The three skips are the two live-evidence gates and an optional installed
Codex filesystem probe. The real Linux worker probes remain separate evidence.
The accounting flag in the verification output reflects offline bookkeeping
checks; it does not assert complete live economic measurements.

No additional live grant usage occurred: 298 turn allowances and approximately
3,506.683 seconds remain. Earlier campaigns, counters and release reports are
retained. Release readiness is **false** until the remaining live and production
support gates have genuine evidence.
