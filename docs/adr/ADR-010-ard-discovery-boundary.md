# ADR-010: ARD discovery and AEEP admission

Status: accepted for the AEEP 0.8 implementation increment, October 2, 2026.
Acceptance records an architecture decision, not protocol conformance or release
approval. Remaining implementation and evidence gates live in
[plan coverage](../../reports/v08/plan-coverage.md).

## Decision

ARD is the primary external discovery protocol. Local fixtures, manual intake,
and other registered discovery adapters remain supported. Operators select the
registry endpoint; AEEP does not ship a privileged public registry. Ordinary
`route()` stays offline and deterministic.

The host plans tasks and supplies bounded semantic actions. Discovery returns
inert candidates. AEEP owns artifact inspection, reviewed semantic mappings,
qualification, comparative evidence, scoped admission, runtime checks and
receipts. A discovery identifier, relevance score or trust claim cannot supply
any of those authorities.

The implementation extends existing registry candidates, assessment definitions,
provider-package ingestion and `ReceiptStore`. It does not add a second planner,
evidence database, approval ledger, or installation service. Protocol-specific
normalization belongs in the adapter. Admission depends on the exact artifact,
behavior, task and environment, so a stable discovery identifier alone never
reuses qualification for changed code or a different model/configuration.

## Inspected upstream contract

On October 2, 2026, `git ls-remote` resolved both `HEAD` and `main` of
`ards-project/ard-spec` to `b76f235a8f461876ad4f1e77abd0eb0eb302b48d`.
The fetched [specification at that revision](https://github.com/ards-project/ard-spec/blob/b76f235a8f461876ad4f1e77abd0eb0eb302b48d/spec/ard.md)
identifies itself as v0.91, Proposal, August 26, 2026. Its SHA-256 is
`6deb2cc58216fb279569d8ff61bd4595ccdf6ceaeef6766a1a1c9f25b6b68a62`.
The [license at the same revision](https://github.com/ards-project/ard-spec/blob/b76f235a8f461876ad4f1e77abd0eb0eb302b48d/LICENSE)
is Apache-2.0; its SHA-256 is
`dfe0e2a538e0e9004d43d1f57598177793109f5662706ccd1b1cb93c7fa34ce5`.

ARD describes entries and registry search. Its domain-anchored discovery handle
has form `urn:air:<publisher>:<namespace>:<agent-name>`; the handle is distinct
from a runtime security principal and artifact location. Search relevance is
separate from trust. AEEP preserves the exact source identifier and registry
provenance, without claiming that an identifier authenticates its publisher.

Only adopted content at this pin defines the compatibility target. Open pull
requests, proposed extensions and current `main` after this pin do not alter it.
Updating the pin requires reviewing the supported subset and compatibility
record. No upstream conformance run is claimed by this source inspection.

## Bounded supported subset

`ARDRegistryAdapter` uses one explicit HTTPS `POST /search`, with a public query,
`federation: none`, one bounded page and local artifact-type filtering. The
implementation caps the response at 1,000,000 bytes and search at ten seconds.
Redirects, referrals and automatic pagination are not followed. Search does not
fetch artifacts, trust documents or JSON-LD contexts. The default namespace is
supported; unsupported context expansion fails closed. Unknown metadata stays
inert. Remote failure may return explicitly configured local candidates, with
the source and failure visible.

This is a client subset, not a complete ARD registry implementation. It neither
crawls publisher manifests nor verifies ARD identity attestations. A public query
must be supplied deliberately; task contents, file paths and credentials must
not be forwarded as discovery context. Missing metadata remains unknown.

## Lifecycle and authority

```text
public discovery intent -> inert source candidate
                        -> pinned local artifact inspection
                        -> reviewed semantic mapping
                        -> existing qualification and comparison
                        -> scoped admission
                        -> task profile and runtime revalidation
                        -> verified outcome and receipt
```

Known candidates can use applicable local evidence without a new experiment.
Unknown or stale candidates return an assessment requirement or abstention. If
an adequate admitted/native route exists, the host can continue with it. No
ordinary task silently installs a candidate or creates assessment authority.

Installed, discoverable, permitted, exposed and used are separate facts. A
deferred tool can still be discovered; a hidden tool may remain reachable.
Call blocking applies only at an enforced dispatch boundary. Claims of absence
also require excluding artifacts, hooks, aliases, endpoints, credentials and
prior context inside the declared execution boundary.

Native controls are compiled by host adapters. Production and experiments must
share profile and dispatch mechanisms. Experiments add independently verified
tasks, controlled differences and accounting under the existing assessment
policy. A complete workflow comparison cannot be inferred from a catalog toggle
or component ablation. Recommendations report conditional evidence and unknowns;
contributor metadata does not authorize compensation.

## Consequences

External discovery failures do not disable unrelated admitted routes. Older
records remain readable, but absent identity dimensions are not backfilled as
observed evidence. Unsupported host boundaries abstain rather than weaken an
isolation requirement. Evidence exports preserve provenance and scope without
publishing task payloads or treating a registry assertion as local verification.

General discovery interoperability fixes belong upstream. Comparative utility,
admission and local policy stay in AEEP. Potentially portable evidence starts
locally and may later support an upstream proposal. The contribution rule in
[AGENTS.md](../../AGENTS.md) governs that distinction.
