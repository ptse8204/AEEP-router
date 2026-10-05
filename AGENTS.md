# Agent instructions for this repository

## Goal

Maintain a secure, provider-neutral system that measures whether adding a capability helps an already capable agent, then scopes approved automatic use. Preserve the compatible execution router, accounting and optional economic features. Keep Codex-specific behavior in adapters.

## Required checks

The operator delegated routine assessment-plan and test-definition changes on
2026-09-25. Record exact reviews under that authority and continue without asking
for each revision. On September 27 the operator also approved the pending assessment-budget
amendment and delegated further finite amendments needed to complete this plan.
Record exact amendments without repeating approval requests. This does not expand
cash spending, disclosure or credential access;
see the standing-authority section in `docs/ASSESSMENT_TESTING.md`.

Before changing execution, assessment, adapters or release verification, read
`docs/ASSESSMENT_TESTING.md`. This policy applies to every agent working in this
repository. Include that path in any delegated-agent brief. Keep implementation
status and remaining gates in `reports/v08/plan-coverage.md`; chat history is not
the project record.

After code changes:

```bash
python3 -m compileall -q src examples tests
PYTHONPATH=src python3 scripts/generate_schemas.py --check
python3 -m pytest
python3 -m coverage run --branch -m pytest
python3 -m coverage report -m
```

## Invariants

- Hard constraints are evaluated before scores.
- Requests cannot weaken manifest policy guardrails.
- `command` uses argv only; never introduce shell interpolation.
- Non-idempotent fallback is off by default.
- Raw resource dimensions remain in receipts.
- Provider claims are not observations.
- Action payloads and output data are not persisted by default.
- Model-facing tool arguments cannot raise operator approval ceilings.
- Benchmarking is not exposed as an unrestricted model tool.
- MCP stdout contains protocol JSON only.
- Modern MCP request metadata/header mirrors fail closed; legacy compatibility remains tested.
- External outcome reports apply only to the selected delegate, are terminal, and are stored once atomically.
- Resource measurements must be finite and non-negative.
- Tool behavior is shared across MCP, CLI, and provider-schema exports.
- Legacy `host` remains delegated; direct host execution uses a separately configured managed-host adapter.
- Subscription capacity defaults to `SELF_ONLY`; unknown capacity never authorizes transfer.
- Codex owns authentication; never read, copy, log, return, or persist Codex authentication state.
- x402 compatibility is offline and disabled by default; it never qualifies or activates a route.
- Protocol details belong in adapters, not routing or assessment decisions.
- Agent/plugin comparisons require separate controlled container workers; different prompts or desktop subagents do not prove isolation.
- Assess a capable shared environment plus a reviewed candidate difference; qualification may force invocation, value trials must leave it optional.
- Freeze structure, adapter, utility dimensions, guardrails, conditions and thresholds before holdout. Never change them to obtain a favorable result.
- Keep answers, future cases, shared writable state and unrelated host configuration outside trial workers.
- Never reset an existing assessment budget or infer measurements from missing evidence.
- Timing pilots cannot qualify, admit, satisfy release gates or supply holdout inputs; retain their costs in the main assessment.
- Protected sign-in is an operator-terminal setup operation on the same grant. Never capture its output through agent tools.
- Ordinary routing must continue without assessment workers. Live and production-support gates require their own evidence.

Read `SPEC.md`, `ARCHITECTURE.md`, and `SECURITY.md` before changing protocol or executor behavior.

## ARD upstream contributions

Classify missing ARD concepts before extending the adapter:

- General discovery interoperability (identifiers, endpoints, manifests,
  federation or conformance) belongs upstream. Prepare an issue or contribution;
  publication still requires explicit user authorization.
- Comparative evidence, task/model cohorts, utility, admission and local routing
  policy belong in AEEP.
- Portable ecosystem evidence starts locally; propose an upstream namespace or
  attestation integration only after the local contract is useful.
- An open upstream pull request is not an adopted interface. Any prototype must
  be optional and cannot silently change the pinned compatibility contract.

Use the source pin and boundary in `docs/adr/ADR-010-ard-discovery-boundary.md`.

## Stack implementation

Follow `docs/STACK_PLANNING.md` and ADR-011 when changing stack orchestration.
Keep task inputs and output contents transient, selected executors fingerprint-bound,
and successor consumption continuous. Do not infer provider setup, admission or
payment authority from discovery or connectivity. Preserve existing task profiles;
stack execution is an explicit reviewed opt-in. Keep real onboarding gaps in the
implementation checklist linked from `reports/v08/plan-coverage.md`.
