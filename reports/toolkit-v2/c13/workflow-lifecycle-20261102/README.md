# Connect reviewed runtime lifecycle to the workflow

The ordinary workflow CLI now previews, sets up, inspects and selectively removes
explicitly selected private Python runtimes using the existing installer and
ledger. It preserves shared consumers, changed user files and interrupted state.
Installation remains separate from enablement, permission, functionality and value.
Read the [operator commands](../../../../docs/aeep-toolkit/STACK_COMPLETION.md#selected-runtime-setup-and-removal).

This increment retains workflow v1 and existing v2 serialization when runtime
bindings are absent. Accounting v2 adds lifecycle stages without creating a grant
or raising existing counters. Canonical export retains original workflow consumer
references. Source/policy drift, revoked authority or uncertain accounting stops
later effects. An ordinary terminal installation failure leaves an independent
runtime eligible; its failed journal is never replayed automatically.

[The source check record](verification-correction/checks.json) is written as the13 required
gates finish. Focused lifecycle/accounting/workflow checks passed76 tests, followed
by35 preparation/lifecycle checks including actual canonical export lineage. The
Framework-context correction subset passed96 checks. Earlier source a8dd37eb
passed1977 tests with21 skips; coverage was deliberately interrupted before the
API correction, so that snapshot has no completed coverage result.
These tests use owned synthetic wheels and are not upstream integration proof.
The working snapshot includes separately preserved CI edits; implementation
commits exclude them. No current-source installed-wheel check has run.

Approved5136b81a installed the retained64-wheel SDK runtime and passed real
LangGraph1.2.14 composition over six owned calls. Its installed-package check
passed and verified all16 ASE source files without invoking ASE. Framework failed
before SDK use because its engineering identity collided with Graph's immutable
record. Approved66848247 then failed before executor start because the first-party
driver omitted a required description. Both Framework attempts are terminal;
no grant or SDK call ran on the latter, and its wrapper timing was not captured.
Do not infer zero time from that missing measurement.

Approved [Framework-only correction482c8c11](../framework-driver-correction-20261102/operation-review.json)
reached the real SDK. It rejected the callback context's `Any` annotation before
any owned dispatch. The current adapter now supplies the concrete optional SDK
`WorkflowContext[dict, dict]`, keeping lazy imports and the same SDK pin. Its unit
substitute now enforces that signature; substitute results remain development
checks, not SDK proof. The failed actual receipt and unchanged runtime are retained.

The [current-wheel/Framework bundle](corrected-sdk-runtime/operation-review.json),
034f218d, prepares one retained environment with the corrected wheel and63 unchanged
dependency wheels. It covers two boundaries, five owned Framework calls and an
installed CLI/schema/source check. Strict-context program preparation, three driver
success/failure/accounting-stop fixtures, package-program preparation and both
standard-library boundaries passed. Approved034f218d passed installation/idempotence, both boundaries, all five
real Framework checks and installed CLI/schema/source verification. Its runtime
is unchanged and retained; all five owned operations are settled. No successful
Graph check was replayed. ASE source verification remains distinct from scheduler
execution. Read the [actual result](corrected-sdk-runtime/execution/summary.json).

The first docs attempt stopped at a locale-dependent argv ordering guard before
lint. Approved correction66848247's next attempt ran markdownlint and found five
extra blank lines. Those guide errors are corrected. Its last authorized docs
attempt is separate from Framework; read the [retained attempt records](../sdk-docs-correction-20261102/).
All historical reviews, receipts, failures, counters and runtimes remain.

[Summary and next actions](summary.json) retain the open full-stack gates.
Both SkillsBench domains still require executable reference/verifier journeys;
real ASE worker dispatch and the remaining upstream components are unfinished.
Comparisons remain paused. No model, service, Docker mutation, credential access,
cleanup, activation, publication or release occurred in this increment.


The seven original reference files for all six selected SkillsBench tasks are now
cached outside worker inputs, with pinned Git object and SHA-256 verification.
[The record](skillsbench-reference-inventory.json) binds79,399 bytes and their
original URLs. They were read only; no oracle, shell installer or verifier ran.
Task-specific rights, dependency closure, grader validation and both actual domain
journeys remain open. The source task pack is unchanged.


All13 current-source gates passed on unchanged e363cfa5:1977 passed/21 skipped
in each full run,83% combined coverage,both branch floors and packaging. The
first actual Framework failure supplied the API correction; it is retained along
with all terminal driver attempts. No third-party pin changed to obtain a pass.
[The six-task transport audit](skillsbench-transport-audit.json) confirms that
original inputs fit existing limits and exclude all verifier/oracle/bundled-skill
files. It sends nothing to a worker and supplies no benchmark result.

The final authorized docs attempt3 passed offline markdownlint and Lychee against
the72 current inputs. Tool bytes are unchanged. [The receipt](../sdk-docs-correction-20261102/docs-attempt-3.json)
retains exact input hashes. No remaining docs attempt is inferred from that success.

The next [scanner work unit](../scanner-runtime-20261102/README.md) built the
retained image and passed containment plus the actual static detection control.
The selected-byte follow-up needs exact84365d39 approval after an empty-input
launch failure. Its four previous charges remain. Read its summary before any
dispatch; no successful SDK/docs check needs replay.
