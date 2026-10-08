# Installation profiles, extension manifests and reversible setup

## User-visible goals

From one CLI/interface, show the full **selected stack** before any effect, including every top-level component, transitive package/install step, license, host/platform compatibility, permission requested, authentication requirement, expected storage/runtime footprint, financial exposure, version/source digest, and uninstall/rollback method. The user explicitly selects components. Metadata lookup must not imply installation or activation. Existing AEEP setup has a reviewed component installer—wrap it where possible.

**Three profiles** (suggested names, not hardwired API commitments):

1. `essentials`: evidence core + one tested skill evaluator + local verification/report generation. The minimum to answer "does this skill help my agent?"
2. `evaluation`: essentials + selected catalog/search, safety scanner, benchmark packs and optional traces.
3. `full`: display all supported optional adapters (router, multi-agent, EvoAgentX, LangGraph, ToolHive, Langfuse, Waza, etc.) and choose a compatible subset. Avoid install-all as a hidden side effect.

Extension capability status is separate from install status: `DISCOVERED`, `NOT_INSTALLED`, `INSTALLED`, `CONFIGURED`, `PERMITTED`, `QUALIFIED`, `BLOCKED`, `ENABLED`, `USED`. Permission control must apply during calls, not merely at catalogue filtering. Unselected entries remain inert.

## Proposed extension manifest example (non-final schema)

```yaml
schema_version: aeep.extension.v1
id: evaluation.agent-skill-eval
role: evaluator
capabilities: [skill.with_without, skill.natural_invocation, usage.tokens, usage.wall_time]
upstream:
  repository: https://github.com/tardigrde/agent-skill-eval
  revision_sha256_or_git_commit: UNRESOLVED_UNTIL_C01
  license: UNVERIFIED_AT_C01
host_support: [codex, claude-code, opencode]
platform_support: UNVERIFIED_AT_C01
adapter:
  kind: reviewed-subprocess
  entrypoint: UNRESOLVED
permissions:
  network: false # must be checked against effective adapter/workloads
  filesystem: scoped
  secrets: []
install:
  action: manual-approval-required
  package: UNRESOLVED
  dependency_lock: UNRESOLVED
  transitive_effects: UNRESOLVED
  rollback: UNRESOLVED
resource_requirements:
  disk_bytes: null
  memory_bytes: null
  metered_calls: unknown
status: candidate-not-qualified
```

This example is **illustrative**, not valid for automatic installation until all unsupported/unknown fields are resolved and a real schema verifies permitted types. The `network: false` example is not a claim that a real skill benchmark can run offline with a remote model.

## Installation approval and safety

`plan` must always be safe and non-mutating. `apply` should require operator review of resolved exact binaries/package hashes/versions, source, permissions and configuration diff. Never generate `curl | sh`, arbitrary lifecycle hooks, implicit `pip install git+HEAD`, or unpinned mutable branch installs as an automatic model action. Favor reviewable argv-only subprocess operations. Respect existing AEEP space reserve and current deployment boundaries. Deduplicate dependencies only when compatible; version conflicts must be visible and reversible.

Installation in a user-scoped Codex/plugin directory can affect other workspaces; disclose effective scope. AEEP cannot claim that merely hiding MCP tool definitions removes packages, skill instructions or credentials from an agent's accessible environment. Sign-in remains owned by the host/user; don't collect passwords or auth tokens through model tools. If runtime cannot satisfy requested isolation, refuse that evaluation evidence tier and explain the blocker.

User experience should explicitly distinguish **installation of toolkit extensions** from **installation of the candidate plugin**. Candidate should remain inspectable and testable in isolated assessment before being offered for normal use. Benchmark datasets needing separate terms or paywalls are opt-in; noncompliant redistribution is prohibited.

## First proposed CLI journey (names subject to C00 inventory)

```text
aeep toolkit list                 # all known extensions and their measured status
aeep toolkit plan essentials     # full non-mutating proposed stack and permissions
aeep toolkit install essentials  # only after operator review, version-pinned steps
aeep eval plan ./candidate-skill  # test plan, baseline, verifiers, possible costs
aeep eval run <reviewed-plan-id> # bounded, approved execution
aeep eval report <run-id>        # comparisons and limitations
aeep toolkit doctor              # readiness/host/connection evidence
aeep toolkit remove <component>  # selective safe rollback
```

Do not claim these commands exist now. Prefer existing `aeep setup`, `aeep stack setup guided`, and other CLI conventions if adapting them is easier/safer than introducing synonyms.

## Installer acceptance tests

- Dry-run changes zero files outside explicit temporary metadata/cache; compare before/after.
- User can review full transitive stack, versions, sources, licensing, permissions, resource/cash unknowns and blast radius.
- A selected incompatible/unsafe extension blocks apply; no partial installed dependency without a recovery record.
- No unselected plugin installed, enabled or reachable through an AEEP-owned bridge.
- Repeated apply is idempotent and does not overwrite user-edited config; rollback validates original/applied/current values and preserves conflicts.
- Essentials works without any optional orchestration/router/marketplace/hosted tracing component.
- Full profile displays compatibility status rather than silently substituting an unavailable engine.
- Offline mode, timeouts, interrupted install, insufficient space, changed artifacts and unapproved expenses all fail closed.
