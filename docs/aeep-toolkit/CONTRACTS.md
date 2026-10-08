# Toolkit contract boundary

C02 introduces inert records for comparing evidence from different evaluators.
They contain identities, hashes and measurement facts. They contain no task
prompts, output payloads, installation commands or execution permissions.

The implementation is `aeep_toolkit.models`, packaged in the existing distribution. Its adapter protocol accepts
an existing reviewed plan ID. Implementations must resolve the current review,
authorization and budget through the assessment service before execution.
A Python protocol cannot enforce that requirement by itself.

## Representation

| Record | Purpose | Authority limit |
|---|---|---|
| `ExtensionManifest` | Pinned source, license/data rights, dependency manifest hashes, host/platform, permissions, effects, resources and rollback | Metadata never installs or enables code. Unknown resources remain null. C03 resolves transitive dependencies and blockers. |
| `AdapterCapabilities` | Exact implementation, supported host/candidate types, optional invocation and telemetry | A conformance reference must resolve to applicable evidence before use. |
| `EvaluationRun` | Exact task/prompt/verifier/candidate/worker hashes, shared configuration, host/model/effort, exposure, invocation, verification, timing and receipts | A completed process does not imply verified success. Control cannot claim candidate access. |
| `EvidenceBundle` | Adapter-bound collection of unique runs | Reject unsupported host/telemetry and duplicate run IDs; retain synthetic/replay/live labels. |
| `ComparisonReport` | Evidence and plan references, verdict, analysis reference and limitations | Demonstrated verdicts require live analysis; validators do not establish statistical significance. C05 supplies the resolver and math. |
| `DeveloperIdentity` | Source-bound identity assertion and optional donation/purchase link | No `verified` boolean accepted from an imported assertion. C12 must authenticate the assertion independently. |

Token observations preserve source-defined subset relationships. Cached input and
reasoning output are never summed into an invented total. Missing categories are
null, and reported categories with unknown overlap semantics are rejected. Timing
keeps agent, verification and setup durations separate and requires provenance.

Cash is a reference to existing accounting, not a new amount field. Resolving that
reference must use the existing receipt/store evidence rules, distinguish estimates
and subscriptions from billed charges, and deduplicate charge IDs. A syntactically
valid digest is not proof that a billing or verifier record exists or is trusted.

## Legacy compatibility

No database migration or historical record rewrite is required. Existing
`ExecutionReceipt`, `ResourceAccounting`, assessment reports and their schema
versions retain their bytes and meanings. A future adapter emits a new toolkit
view referencing those records. Missing legacy host, exposure, token or billing
provenance stays unknown; it cannot be backfilled as observed zero or conformance.

The model module uses the existing Pydantic dependency with the same strict-field
and finite-number policy. It has an independent Python namespace because the
legacy initializer has eager imports and order-sensitive circular dependencies.
A subprocess test verifies that importing the contracts does not import `aeep`.
Existing exports remain unchanged. This is one distribution and one repository;
no new dependency, server or database is introduced. The full Essentials journey
still requires C03-C06.

## Remaining C02 checks

The inert registry rejects duplicate IDs and looks up explicit extensions.
Bundle validation binds candidate bytes and rejects unsupported host/adapter
identities or telemetry. Twenty-six focused checks pass on integrated source;
full checks are running under `reports/toolkit-v2/c02`. C02 remains IN_PROGRESS
until they finish. Canonical evidence resolution belongs to C04/C05; no reference
is trusted merely because these schemas accept it.
