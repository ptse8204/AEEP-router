# C00 implementation inventory

Use the existing execution and evidence controls to build the evaluation journey.
The first boundary to change is package loading: importing `aeep` currently loads
routing, managed hosts, economic code and assessment together. Merely adding
extension names would leave Essentials coupled to those modules.

## Observed baseline

The local and remote `main` both resolved to
`8b015bf0247d4d9f49038982c49f3711a2802d97` on October 8, 2026.
Work continues in `/Users/edwintse/Documents/aeep-toolkit-v2`, branch
`codex/toolkit-v2-implementation`. The original checkout has unrelated edits;
[the snapshot](../../reports/toolkit-v2/c00/workspace.json) lists them.
They are excluded from this branch.

The first managed worktree was beneath `.codex/worktrees/toolkit-v2`.
`assessment.identity.protected_directory` correctly refused to fingerprint its
runtime there. Ordinary pytest recorded 116 failures, 1,177 passes and 21 skips.
The replacement worktree leaves that protection unchanged. Keep both attempts;
the path failure does not justify relaxing credential protections.

Python is 3.13.1 on macOS arm64. The global Python distribution metadata reports
AEEP 0.5.0, while this source tree is 0.8.2; checks explicitly use `PYTHONPATH=src`
or pytest’s configured source path. Neither the global package nor the separate
desktop runtime is upgraded by this task. The free-space snapshot is above the required
50 GiB reserve. No images, containers, services or dependencies were installed.
The existing authoring tools and Python environment are reused. Current results
and exact commands are in [checks.json](../../reports/toolkit-v2/c00/checks.json).
Skipped container/native/live tests remain unverified.

## Module disposition and ownership

“Owner” below identifies a code boundary, not a person. The complete
[import map](../../reports/toolkit-v2/c00/modules.json) records each Python file,
its SHA-256, line count and direct imports at the base revision.

| Module boundary | Decision | Owner and dependencies | Behavior/evidence and migration risk |
|---|---|---|---|
| `models.py`, `accounting.py`, `attempts.py`, `store.py` | REUSE | Core contracts and SQLite; Pydantic, Decimal, cryptography | Raw usage, cash provenance, atomic attempts and migrations. Preserve serialized historical meaning; reuse references rather than another ledger. |
| `assessment/models.py`, `repository.py`, `identity.py` | REUSE | Assessment definitions, reviewed digests and grants | Immutable definitions, finite allowances and source drift. Missing identity cannot be upgraded during normalization. |
| `assessment/service.py`, `benchmarking.py`, `assessment/reporting.py` | WRAP | Evaluator adapter; imports Router and qualification | Existing controlled trials, grading and uncertainty. Keep this implementation inside the optional evaluator; do not claim router-free execution yet. |
| `assessment/intake.py`, recipes, contained extensions | REUSE | Candidate inspection and independent grading | Static intake is inert; executable recipes need review and containment. A skill file is untrusted input. |
| `execution.py`, `executors/`, `hosts/` | KEEP | Optional execution adapters and host integration | Native command boundary, Codex protocols, controlled workers and cancellation. Experimental host support remains separate from software tests. |
| `router.py`, policy, scoring, qualification, estimator | KEEP | Optional legacy routing extension | Hard constraints precede scoring; late dispatch checks remain mandatory. Preserve imports and old CLI behavior. |
| `stack_models.py`, `stack_planning.py`, `stack_runtime.py`, `workflow.py` | KEEP | Optional orchestration; Router, attempts and store | Reviewed serial DAGs and transient artifacts. No dynamic-loop equivalence claim. |
| `component_setup.py`, `installation.py`, `onboarding.py`, `connections.py` | WRAP | Operator installation and rollback | Exact component review, space reserve, argv commands and conflict preservation. Current preview does not enumerate locked transitive dependencies: C03 must report that gap. |
| `discovery.py`, `discovery_service.py`, `catalogs.py`, `marketplaces.py`, `legacy_discovery.py` | KEEP | Optional discovery; bounded network adapters | Inert catalog records; no implicit installation. Preserve ARD pin and MCP Registry `/v0.1/servers` subset. |
| `telemetry.py`, `instrumentation.py`, `profiler.py` | REUSE | Local OTel API and trace normalization | Existing minimized traces; exporters remain optional. Provider-reported usage is not billing evidence. |
| `economic/`, `payments.py`, `capacity/`, `x402/`, `market_server/` | KEEP | Optional economics and capacity | Existing compatibility and authority tests remain. Subscription units are not cash; x402 remains offline. |
| `provider_package.py`, `provider_ingest.py`, `artifact_store.py` | REUSE | Provenance and content-addressed artifacts | Signed claims remain claims; acceptance does not activate a route. Useful later for portable evidence. |
| `cli.py`, `__init__.py`, MCP and provider exports | WRAP | Public entry points; currently eager imports | Add a small toolkit entry point and preserve all exported names. Check cold imports before claiming a minimal core. |
| `integrations/aeep`, DSH, managed-worker assets | KEEP | Host-specific adapters | Native host controls and installer assets remain version-bound. Editing packaged assets invalidates applicable historical evidence. |

No module is selected for deletion or archival at C00. Replacement requires an
adapter proof and rollback checks. The project has nine mandatory Python runtime
dependencies; FastAPI/Uvicorn are an optional server extra. No upstream evaluator,
workflow framework or hosted trace service is a current package dependency.

## Existing evidence and authority

The baseline contains 1,314 collected tests and retained campaigns under
`reports/v08`. Historical DOCX/workbook failures and incomplete human/release
checks remain valid records of their original revisions. The documentation
revision recorded 1,293 passes and 21 skips; this track runs its own baseline.

The September 25/27 delegation covers routine finite test-definition amendments.
It does not authorize new paid execution, disclosure, credential access or release.
No grant was opened or altered here. New live V2 studies require a reviewed
plan and current worker conformance before reservations or calls.

Installed host readiness, authentication, active worker ownership and whole-host
resource use have not been probed. C00 does not start managed hosts to inspect
inventory: that can initialize external MCP processes. Existing source and
historical records identify native Codex/macOS as the production target, with
Codex/Claude/DSH/API connection code and Linux/WSL installer paths. Compatibility
code and historical reports do not qualify a new V2 installation.
