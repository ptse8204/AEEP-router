# Stack planning and execution

The host interprets the user's task and submits a `GoalSpec`: deliverable node
IDs, a semantic DAG, typed ports, bindings, constraints and verification needs.
Private task values arrive separately when execution starts. AEEP selects from
configured eligible executors; it does not make another model call.

`StackService` provides `propose`, `inspect`, `optimize`, `preflight` and
`compile`. `StackRuntime` provides `assemble`, `run` and `amend`. Proposals and
successors are content-addressed records in the existing receipt database.
A reviewed, active stack-enabled task profile can cover the selected configuration
without another proposal review. Otherwise review uses the existing exact-definition
review command. Explicit proposal revocation still blocks execution. No stack operation
can create an admission, grant or payment approval.

## Try the offline journey

```bash
PYTHONPATH=src python3 examples/stacks/demo.py
```

The media fixture produces a Windows XP-style edit decision list with a
12-second timeline, matching audio duration and continuity checks. It does not
encode video. The data fixture groups three rows into a verified report. The
research fixture extracts facts from two fixed documents and checks reference
coverage. Its URLs identify fictional fixture documents; it does not retrieve
live information. These tests exercise one planner across three graphs, without
establishing provider quality or the benefit of using AEEP.

To create files for the CLI example:

```bash
PYTHONPATH=src python3 examples/stacks/export_fixture.py data /tmp/aeep-stack-demo
aeep stack -m /tmp/aeep-stack-demo/manifest.json propose /tmp/aeep-stack-demo/goal.json
```

Keep the returned proposal ID. These commands show its current requirements:

```bash
aeep stack -m /tmp/aeep-stack-demo/manifest.json inspect PROPOSAL_ID
aeep stack -m /tmp/aeep-stack-demo/manifest.json preflight PROPOSAL_ID
aeep assess -m /tmp/aeep-stack-demo/manifest.json review PROPOSAL_DIGEST
aeep stack -m /tmp/aeep-stack-demo/manifest.json assemble PROPOSAL_ID
aeep stack -m /tmp/aeep-stack-demo/manifest.json run PROPOSAL_ID /tmp/aeep-stack-demo/inputs.json
```

Use the `proposal_digest` from preflight for exact review. These are operator
commands. A `GoalSpec` defaults to `propose_only: true`, which blocks assembly
and execution even after review. The demo explicitly sets it false. To change
an existing goal, propose a new goal file with `--parent PROPOSAL_ID`; review its
new digest. `optimize PROPOSAL_ID --policy cost` also creates a successor.

## Configuration search

Executors declare typed ports under `config.stack.inputs` and
`config.stack.outputs`, plus optional `config.stack.setup_ids`. These are
operator configuration, not registry instructions. A callable host or delegate
may satisfy a node without adding a capability. Unsupported host capabilities
are not treated as callable. Discovered candidates still require ordinary
intake, applicable evidence and local registration before selection.

Search applies router eligibility and hard constraints before policy scoring.
It keeps eight candidates per node and a beam of 32 by default. Operator-owned
`StackPlanningConfig` limits graph bytes, elapsed search time and expansions;
models cannot change those limits. Aliases `cost`, `quality`, `speed` and
`privacy` use existing policies. Privacy additionally requires local execution
without network access. A configured policy with that name retains its weights.

An operator can list approved one-hop `converter_ids`. A converter becomes a
separate node with its own fingerprint, authority, estimate and attempt. The beam includes eligible converter alternatives and prunes partial configurations
against aggregate limits. Candidate or beam truncation reports incomplete search.
An empty result is never a proof of global infeasibility.

Artifact compatibility compares semantic type, media type, encoding, locality,
confidentiality and declared upper bounds. Its conservative JSON Schema subset
supports simple types, properties, required fields, boolean additional-property
rules, arrays, enums and scalar/length bounds. References, unions and unsupported
relationships remain unknown. Unknown edges block execution. Registry examples
do not prove compatibility. Runtime validates materialized values and byte
bounds; media dimension limits require a supported verifier and currently stop
execution rather than accepting unverified dimensions.

Resource and cash estimates include selected converters and reserved retries.
They remain estimates for unresolved inputs. First-release execution accepts
confirmed-free configurations only. Paid aggregate reservations, remote HTTP/MCP
production adapters, and physical resource ceilings requiring a new containment
boundary remain separate gates. Subscription usage is never converted to cash.

## Authority and recovery

Assembly can reuse a specified reviewed capability profile with the exact
executor fingerprints. Its existing activation and native task scope still
control execution. Without a profile, the operator CLI retains ordinary
per-action authority; assembly does not create standing authority. The model
execution tool is exposed only through an active task binding. Task scope v1
still supports reviewed native sandbox commands only.

Nodes execute serially. Their actual inputs are bound after dependencies finish;
the runtime rechecks the proposal, setup, admission and fingerprint before each
dispatch. Callable local nodes use the existing prepared-decision workflow path.
Host/delegate nodes use the existing waiting-decision and terminal-outcome path.
Each node allows only its selected executor. A change of implementation requires
a reviewed successor, not silent fallback.

SQLite migration 9 adds `stack_runs` to `ReceiptStore`. Its transactions claim
one active run, reserve attempts before dispatch and preserve a fixed deadline.
Concurrent and duplicate requests cannot launch a second copy. Failed idempotent
read-only nodes may consume a reserved retry. Successful predecessors are reused.
Cancellation or uncertain execution stops the stack. Existing attempt recovery
must resolve uncertain effects. To recover a lost checkpoint after a successful
dispatch, stop the old coordinator and record a `StackRecovery` with exact receipt
IDs and the retained output digest. `recovery-define` stores it for ordinary
exact review; `reconcile` accepts it only with verified successful receipts for
that node and matching output. It never refunds allowance or converts an
uncertain effect into success. Operator observations remain identified as such.

Default records contain graph structure, definition digests, selected identities,
receipt references and output digests. They contain no materialized task inputs
or output contents. Keep `completed_outputs` from the result in host-managed
storage if recovery is needed. Supply that object to:

```bash
aeep stack -m MANIFEST resume PROPOSAL_ID INPUTS_JSON COMPLETED_OUTPUTS_JSON
```

A missing or changed completed artifact blocks resume. The runtime never
regenerates it. For a waiting delegate, add `--delegated DELEGATED_OUTPUTS_JSON`,
mapping the waiting node ID to its terminal output. Existing outcome checks
apply. `amend PREVIOUS_ID SUCCESSOR_ID` preserves consumed attempts and the
original deadline. It invalidates affected descendants and refuses to repeat
completed consequential work. Run state is included in campaign snapshots.

## Provider setup

`ProviderSetupService` accepts operator-registered definitions for an exact
non-charging HTTPS GET, a pinned local executable version check, or a trusted
host-managed callback. Definitions bind the adapter revision, endpoint or
executable digest, required observations, timeout and observation lifetime.
Changing adapter code invalidates the previous readiness result.

```bash
aeep stack -m MANIFEST setup define SETUP_JSON
aeep assess -m MANIFEST review DEFINITION_DIGEST
aeep stack -m MANIFEST setup inspect SETUP_ID
aeep stack -m MANIFEST setup check SETUP_ID
```

Use the digest returned by `setup define`. Requirements appear together in stack
preflight. Sign-in and billing URLs hand control to the host/provider interface.
Credentials are operator-owned environment bindings; do not paste credentials
into a goal or model conversation. No Codex authentication is accessed. A
successful login does not establish billing, admission or spending authority.
The HTTPS adapter can inspect a reviewed numeric credit field without retaining
the raw response. An unknown billing state remains a blocker when required.

Every check stores a content-free intent before contacting the provider and a
sanitized observation afterward, including cancellation or failure. Readiness
expires. A host integration must inject its versioned callback into the setup
service and pass that service to `StackService` for preflight.

This increment performs no generic installation or container provisioning.
Unsupported provisioning produces a handoff requirement. Existing profile
lifecycle manages its own owned changes; provider-specific installers and their
partial rollback records require a reviewed adapter. Before installations or
image operations, preserve the 50 GiB host reserve and inspect Docker usage.

## Discovery and interfaces

`DiscoveryService.from_config` and the registry CLI share `discovery_adapter`.
Configured sources support ARD, fixtures, the MCP Registry, Docker catalogs,
Smithery and explicit local provider packages. Remote sources require explicit
permission and destinations. Queries contain public capability descriptions.
Candidate metadata cannot install code, register adapters or establish admission.
The MCP Registry contract retains `/v0.1/servers`; legacy provider registries
remain available through `legacy_discovery` and compatibility re-exports.

Shared schemas expose `aeep_stack_propose`, `aeep_stack_inspect`,
`aeep_stack_optimize` and `aeep_stack_preflight`. A reviewed profile with `stack_execution: true` can activate a task service that
also exposes `aeep_stack_run`; its arguments cannot change operator ceilings or
perform setup. Use the operator CLI or Python runtime for recovery. Ordinary
single-action routing does not run stack search or assessment workers.

## Release evidence

See [the implementation checklist](../reports/v08/stack-implementation-checklist.md)
for current checks and incomplete gates. Free access checks on existing host
connections do not prove a new sign-in handoff or API-key billing setup. The first
release remains incomplete until those actual onboarding paths pass. Remote paid
production, controlled three-way value trials and archive migration follow under
their own authority and evidence requirements.
