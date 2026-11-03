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

## Implemented private wheel runtime

The local CLI can now prepare, install and remove a selected Python wheel closure.
Use the same registry selection and policy as `plan`; supply a wheel inventory
with `extension_id`, `filename`, `name`, `version` and `sha256` for every selected
component and dependency. Each wheel hash must match its manifest. Preparation
reads local wheels and the interpreter without starting either or writing files.
The destination must be absent and its parent must already exist.

The default reserve remains 50 GiB. A temporary operator exception uses a v2
installation plan and binds one exact destination, filesystem device and wheel
set. It expires within 24 hours and declares a lower reserve and a maximum
additional allocation reservation. It grants no execution, model, service or
cleanup authority. Pass its reviewed JSON file to `install-plan` with
`--storage-exception /absolute/storage-exception.json`; review the entire new
installation digest before `install`. V1 plans retain their original meaning.

Preparation and installation read actual usable capacity. Installation rechecks
the floor and observed host free-space change between steps; other host activity
can therefore stop it. These checks cannot interrupt an in-progress pip step and
do not establish a continuous peak-usage bound. Failed or expired work retains
its journal and is not retried automatically. Expiry does not prevent removal
of an unchanged owned runtime. The same exception cannot authorize another
destination, filesystem or wheel set.

```bash
PYTHONPATH=src python3 -m aeep_toolkit.cli install-plan \
  --preview selected-preview.json --policy policy.json --wheels wheels.json \
  --wheelhouse /absolute/reviewed-wheels --destination /absolute/new-runtime
```

Save that output as `installation.json`. Review its complete selected manifests,
policy, wheel inventory, interpreter and destination. The operator command then
requires the exact `review_sha256` from that document:

```bash
PYTHONPATH=src python3 -m aeep_toolkit.cli install \
  --installation installation.json --reviewed-digest REVIEWED_SHA256
PYTHONPATH=src python3 -m aeep_toolkit.cli remove \
  --installation installation.json --reviewed-digest REVIEWED_SHA256
```

Installation uses standard venv/pip with only staged, hash-checked local wheels.
The installed `packaging` 24.2 library checks wheel tags, Python requirements and
the complete selected dependency closure before effects. Pip installs with
`--no-deps --no-index` and checks installed dependencies afterward. Active direct
URLs and dependency extras are rejected. Source builds,
Python startup hooks and general wheel `.data` relocation are rejected. The
reviewed `aeep-agent-router` wheel may place its exact-version
`.data/data/share/aeep/...` documentation and examples inside the private runtime.
Other distributions, versions and relocation schemes remain unsupported; these
shared assets participate in the same whole-tree edit-preservation checks.
No host connection is written or enabled. The 50 GiB free-space reserve is checked
before effects, with at least 500 MiB installation headroom.

The sibling `.aeep-install.json` journal and lock remain after removal. Repeating
a successful install verifies the complete recorded runtime tree before returning
its prior result. Failure or interruption requires inspection; it cannot silently
retry. Removal requires the exact applied file bytes, modes, directories and
symlink targets. Stop processes using the runtime first. Changed files, additions
(including caches), hard links and special files block removal and are preserved.
An interrupted removal stays unresolved rather than authorizing a broad cleanup.

Private installation supports macOS with an unambiguous version and glibc Linux.
It refuses tag-discovery paths that would spawn a compatibility probe, including
musl and legacy macOS version ambiguity. Windows private installation remains
unsupported. Archive paths are checked for case-insensitive collisions.

This is an operator CLI, not a model-facing installation tool. Its digest binds
reviewed inputs; it is not a signature or third-party qualification. Non-wheel
extensions and new platform/package combinations still require their own reviewed
installation and compatibility proof. Installed does not mean enabled or qualified.

The space preflight derives a lower reservation from actual wheel archive and
expanded sizes (including allocation rounding and staging), plus 500 MiB bootstrap
headroom. A smaller manifest estimate cannot lower this reservation. This is an
installation planning bound, not a measured runtime footprint.

## Inspect candidate bytes separately

```bash
PYTHONPATH=src python3 -m aeep_toolkit.cli candidate /absolute/skill/SKILL.md
```

The command prints file hashes and a whole-payload identity without printing skill
contents or executing code. It excludes `evals`, `.git` and `__pycache__` directories
at every depth. The same captured files supply later private staging, so excluded
files cannot escape the identity check and reach a worker. Links, special files,
credentials, ambiguous paths and oversized payloads are refused. This does not
install the candidate in a host or certify its safety or benefit.

Unknown memory blocks preview by default. An operator may explicitly set
`allow_unknown_memory: true` in the preview policy to acknowledge that uncertainty.
The acknowledgment is included in the exact review digest and the preview's
limitations; memory remains null. It does not waive disk reserve, package or
permission checks, or authorize execution. Existing policies omit the false
value when serialized, preserving prior installation review hashes.
