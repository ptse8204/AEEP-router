# ADR-011: Stack synthesis and provider setup

Status: accepted for implementation, October 4, 2026. This is not a release,
qualification, provider onboarding, or payment approval.

## Decision

The host supplies a typed semantic task graph. AEEP selects a bounded compatible
configuration using existing eligibility, policy, evidence and scoring. Proposals
are inert, immutable compilation products. They cannot grant authority, install
software, invoke production tools or start assessments.

Use the existing workflow engine, exact-definition repository, task profiles,
attempts and receipt store. Prepare individual routes only after their real inputs
exist. Pin each selected implementation and recheck it at dispatch. Persist graph
structure and digests, not task inputs, credentials or intermediate outputs.
Recovery requires matching completed-output handles and never replays uncertain
work. First-release execution is confirmed-free; paid remote execution remains a
separate adapter, authority and conformance milestone.

DiscoveryService is the canonical new discovery entry point. Its operator-owned
source factory also serves the CLI. Legacy provider discovery remains a
compatibility surface. Metadata cannot establish admission or load adapter code.

Provider setup is a separately registered adapter interface. Requirements,
observations, authentication handoffs and non-charging checks are distinct from
execution readiness. Use operator-owned host login and secret bindings; never
read Codex authentication. Unsupported setup remains a visible blocker.

## Delivery and evidence

Deliver contracts/search, compiler/recovery, unified discovery/setup, shared
interfaces, then media/data/research fixtures. Real onboarding requires actual
operator setup and non-charging checks. Mocks prove only software behavior.
Record progress and unresolved gates in reports/v08/plan-coverage.md.

Keep router/policy, contracts, profiles, workflows, attempts and receipts in core.
Assessment campaigns, economic settlement, market servers and x402 are optional
current features. Historical schema readers and provider discovery are
compatibility code. Live diagnostic scripts are experimental evidence support;
reports and generated schemas are historical/generated artifacts, not deletion
candidates. No code or evidence is classified removable without dependency and
restoration checks. Package splitting and evidence migration follow delivery.

## Compatibility

Existing action/workflow schemas and task-scope v1 authority retain their meaning.
Add independent stack schemas and content-free state in the same SQLite store.
Ordinary action routing does not import or invoke the planner. No new planner
model, permission engine, payment service or arbitrary-shell installer is added.
