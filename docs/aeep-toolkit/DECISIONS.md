# AEEP Toolkit architecture decisions (living log)

These are **proposed steering decisions**, not claims of implemented features. Append dated ADR-style entries to document new evidence and decisions. Do not retroactively edit benchmark parameters or rewrite historical AEEP records.

| ID | Initial decision | Reason | Reconsider if |
|---|---|---|---|
| D01 | Product is evidence-first plugin-value assessment and developer support | Original purpose; user-visible differentiation | User changes mission |
| D02 | Existing AEEP monorepo; feature branch; no full fresh-start rewrite by default | Preserve tests, history and reusable modules | C00 shows core cannot be safely isolated |
| D03 | Tiny core, modular AEEP extensions, optional legacy router | Avoid supporting two general-purpose agent platforms | C01 proves mandatory core needs a function |
| D04 | One benchmark engine first, chosen by measured adapter spike | Integration quality > number of libraries | Real trials favor a different engine |
| D05 | Natural selection control/treatment is primary evidence; forced-use separate | Prevent overstating optional capability benefit | Do not weaken this without explicit scientific rationale |
| D06 | Unknown cash/tokens are null; separate telemetry/estimates from actual spending | Prevent invented savings | Never overwrite missingness |
| D07 | Existing security/assessment authority remains in force | Product change does not create permissions | Only an explicit operator decision can revise it |
| D08 | Installation is preview-first with explicit component selection | Users must know the stack they are installing | Review tested user feedback |
| D09 | Full Toolkit is a catalog/profile, not install-everything-by-default | Some components are heavy, licensed, metered or host-incompatible | Only if all qualify on a target host |
| D10 | No new payout ledger/credit economy in early release | Funding is separate from resource savings | Proven user/developer demand |
| D11 | Static HTML/Markdown value reports first | Avoid hosting complexity | Users require an interactive report |

## Decision entry template

### DNN — YYYY-MM-DD — [title]

- **Status:** proposed / accepted / superseded / blocked
- **Problem & product impact:**
- **Alternatives:** (reuse / wrap / write / defer)
- **Observed evidence:** pinned URLs, commits, tests, license, interface results
- **Decision and rationale:**
- **Consequences, migration, rollback:**
- **Checkpoint linkage:** Cnn

### D12: 2026-10-08, retain authority and isolate package imports

Accepted for C00/C02. Keep the current receipt store, assessment repository,
accounting and controlled runner. Add versioned evaluation records as views and
references; do not migrate or re-sign historical evidence. The inventory found
eager package exports importing routing and host modules. A minimal import path
must be verified before claiming Essentials independence. Existing callers and
serialized records remain compatible.

### D13: 2026-10-08, evaluator candidate and fallback

Accepted source-level decision for C01; runtime qualification remains open.
Inspect agent-skill-eval 0.7.0 at `59de161f657b82bfaf8f6abe83dfff38552deb21`
through a narrow adapter first. Its optional invocation matches the question, but
its workspace and final-output accounting do not meet AEEP controls by themselves.
Use AEEP's existing runner as the fallback. Waza's Copilot coupling and SkillRank's
forced prompt increase first-adapter scope. The pinned source matrix records the
comparison. No external engine is installed, enabled or approved by this decision.

### D14: 2026-10-08, additive contracts before engines

Accepted implementation scope for C02. Reuse Pydantic, receipt references and existing accounting semantics. Introduce only extension metadata,
adapter capabilities and content-free evaluation/report envelopes. Validators
check structure and consistency; a claimed evidence reference never authenticates
itself. Repository resolution and trust checks remain mandatory before a report
can claim verified billing, independent verification or conformance. No new ledger,
planner, process manager or exporter is needed for these contracts.

### D15: 2026-10-08, independent imports within the existing distribution

Accepted for C02. Place inert models in `src/aeep_toolkit`, using installed
Pydantic with the existing extra-field and finite-number validation policy.
Importing `aeep.models` first executes the broad legacy initializer. A temporary
lazy-export experiment exposed an order-dependent provider-package/economic
import cycle. That experiment was not applied. A separate namespace costs one
small model base and preserves every legacy export. Setuptools already discovers
packages under `src`; no distribution split or new dependency is needed. Test
minimal imports in a fresh process and include this namespace in branch coverage.
Rollback removes the new namespace and its schema exports without rewriting any
legacy record.

### D16: 2026-10-08, local CLI delivery confirmed by operator

Accepted by the operator in this continuation: local Python CLI with static
HTML/Markdown reports first; a browser interface may follow. Keep the small core
independent of deployment UI, with existing receipt/accounting storage behind
adapters. No hosted database, web service or cloud deployment is needed for the
first product. Controlled comparative execution still needs separately reviewed
workers. This decision adds no installation, credential, model or release authority.

### D17: 2026-10-08, pure preview before installer integration

Accepted C03 implementation scope. Existing `component_setup.preview` requires a
Router/store, and its package installer does not lock transitive artifacts. Reuse
its existing operator review and recovery path later; do not call it from a dry
run. Add a pure dependency/permission preview using C02 records, installed
Pydantic and the existing canonical JSON digest convention, plus a small argparse entry point. It consumes explicit metadata,
never imports extension code, invokes package managers or opens host configuration.
A source pin without an artifact/dependency review stays blocked. Three profiles
filter available roles; Full does not select anything automatically. Actual apply
remains unavailable until exact effects can pass the existing installer authority
checks. Tests cover dependency closure, policy conflicts and zero side effects.

### D18: 2026-10-08, restore external evaluator first

Accepted correction following the operator's objection. Withdraw the proposed
shared execution-service extraction and the associated architecture question.
Legacy Router coupling is a fallback limitation, not evidence against the preferred
external candidate. Follow D13: prepare and run the bounded agent-skill-eval spike
with its existing fake harness before choosing additional internal infrastructure.
A catalog entry, schema or synthetic adapter double is not upstream integration.
No new runner, installer or workflow engine is justified by the current evidence.
Keep the local CLI/report choice under D16. C03 stays unfinished and C04 remains
unqualified until their recorded acceptance checks pass.

### D19: 2026-10-08, executable development stack in one integration directory

Accepted implementation under the operator's request to actually build and
showcase the stack, following the concrete bounded setup review. Consolidate
`integrations/toolkit` around the published agent-skill-eval wheel, a complete
24-wheel lock, standard venv/pip setup and its actual CLI. All 16 evaluator source
files match the C01 pin. The private setup was authorized by this follow-up; no
new live, credentials, cloud or release authority is inferred.

Reuse the upstream scheduler, fake harness, deterministic graders and report
command. Add a development-only bridge that verifies the fixed synthetic suite
and renders the stack/evidence report. Its commands cannot select live models or
arbitrary candidates. This is not the general EvaluatorAdapter or an alternative
approval/installation service. Ten finite offline tests cover failure, subject
drift, exposure, missing runs, grading disagreement, timeout and report labels.
The existing test-definition delegation applies to those tests.

The original nine-wheel scratch supplement was replaced by a fully isolated
24-wheel runtime for reproducibility. Existing host packages remain unchanged.
The observed all-error/zero-exit upstream run is retained; successful fixture runs
do not establish controlled Docker workers, canonical receipts or model benefit.

### D20: 2026-10-08, operator's 14 component assignments are explicit

The operator restated the preferred solutions and responsibilities. Encode all
14 in the development manifest and render them directly in the showcase with
actual status. Restore the omitted GitHub Sponsors support mechanism, retain
BenchmarkRunner as fallback, and keep workflow execution/proposal/optimization
and MCP/trial isolation distinct. Optional status is not completion or permission
to replace a named upstream with new internal infrastructure. This presentation
correction does not implement the outstanding adapters or install other packages.

### D21: 2026-10-08, audit original requirements before resuming implementation

The original ZIP was reread in full at the operator's request. All nine planning
files had been imported, but the C01 matrix rewrite omitted Sponsors, the
already-deferred Archestra entry and the detailed review worksheet. Restore those
requirements and preserve exact archive snapshots and checkout diffs. Reopen C01
while completing its required per-candidate review; retain existing source facts
and historical test evidence. The master plan already specified the upstream
stack, local reports and continuous safe implementation. It did not require the
operator to choose a new architecture before the external adapter was tested.

[The audit](HANDOFF_AUDIT.md) records incomplete setup, adapter, comparison,
three-family journey and optional-pack work separately from actual omissions.
Keep the development demo's fixed evidence format out of the production contract;
connect the existing reviewed installer, receipts and workers through the common
adapter. Conditional optional integrations remain visible. Archestra remains
deferred research, and no new third-party execution is authorized by this audit.

### D22: 2026-10-08, connect upstream fixture execution to existing receipts

The operator approved the audit correction. Reuse `CommandExecutor`, execution
journals, `ExecutionReceipt`, `ReceiptStore` and `AssessmentRepository` for the
bounded agent-skill-eval fixture batch. Agent-skill-eval continues to schedule and
grade its trials; no new runner, approval database or routing configuration is
needed. Add only the translation from checked fixture artifacts to C02 records.
A batch receipt describes coordinator execution, not individual model usage.
Keep model metrics unavailable and worker containment unverified. This increment
is fixture-only; it neither implements live dispatch nor completes C04.

The finite regression review covers failed and timed-out coordinator processes,
receipt/artifact drift, both arms, independent verification, and synthetic-only
normalization. Existing test-definition delegation applies. No grant, historical
receipt, candidate package, host setting or live budget is changed.

### D23: 2026-10-08, reuse onboarding's read-only inventory for toolkit doctor

The existing `onboarding.inventory` already reads project connection metadata
without starting services. Reuse it for `aeep-toolkit doctor`; do not call
`check_setup`, which constructs Router/store instances. Return only bounded names,
configuration/enabled facts and explicit unknown installation, live exposure and
qualification states. A digest of the sanitized observation is provenance for
that view, not proof of installed package integrity. This implements one C03/C06
diagnostic step without new dependencies, host configuration writes or authority.

Finite checks cover each existing host format, disabled and malformed entries,
secret-field exclusion, missing configurations, and absence of process/network/
store effects. They use the existing test-definition delegation.

The inventory path exposed a blocking FIFO open in the shared project-config
reader. Add `O_NONBLOCK` before its existing regular-file/hard-link/size checks;
all callers retain their validation and regular-file behavior. The new diagnostic
translates legacy configuration errors into a bounded CLI error and remains
explicitly unsupported where `O_NOFOLLOW` is unavailable. A real named-pipe and
symlink check covers refusal without reading their content. Historical host
bindings are not requalified by this change.

### D24: 2026-10-08, bind coordinator receipts to recorded selection decisions

The first fixture bridge used an explicit placeholder decision ID because it did
not route. Replace that placeholder with the existing `RouteDecision` record for
the fixed reviewed executor, using `BYPASS_ROUTER` / `pinned_executor` and no
ranking. Save it before dispatch and retain an immutable assessment-record
snapshot. The verifier resolves action and selected-executor identity through
that decision as well as the receipt and artifact hashes. A changed decision is
rejected. This adds no Router instance, selection algorithm or execution authority.
Earlier fixture reports remain source-bound historical records; they do not
satisfy the stronger new verification merely by retaining the same schema names.

### D25: 2026-10-08, inspect the selected runtime without starting it

Reuse the toolkit's bounded metadata reader and Python's standard email parser
for installed distribution metadata. The development bridge currently starts the
selected interpreter before containment simply to read versions. Replace that
probe with filesystem inspection of the pinned runtime, package metadata and the
sixteen reviewed evaluator source files. Expose the same result through an
`inventory` command. Bind package metadata to the existing hash lock; do not add
another package manager, installer journal or execution authority.

Metadata matches do not attest dependency code, the interpreter or containment.
Report those limits and reject unexpected startup hooks, duplicate distributions,
source drift, linked/special files and mismatched versions before fixture dispatch.
The finite regression review covers zero process/network/configuration effects,
malicious metadata, missing distributions and exact lock/manifest binding under
the existing test-definition delegation. This does not authorize another package
installation or qualify a real host. Existing runtime and evidence remain intact.

### D26: 2026-10-08, connect normalized evidence to descriptive reports

Use the C04 fixture adapter's C02 records to produce reusable local JSON,
Markdown and HTML summaries. The existing `assessment.reporting.fit_report`
and `paired_interval` remain the inference path: they require reviewed campaign,
recipe, holdout and ledger inputs that a standalone EvidenceBundle does not
resolve. Do not invent substitutes or issue a benefit verdict from declared
references. The small `aeep_toolkit.reporting` module groups exact cohorts,
checks observed pairs and reports counts, token categories and timing coverage.
It performs no execution, installs or remote lookups. All verdicts remain
NOT_ASSESSED until the existing reviewed-analysis path is connected.

This is safe independent C05 work on the standardized C04 fixtures, while C03/C04
remain open. Test unknown/missing evidence, mismatched hosts and prompts,
duplicate arms, worse success with fewer tokens, overlapping token categories,
zero successes, long-tail timings and escaped report content under the standing
finite-test delegation. Unresolved billing references and plugin fees stay
unknown; neither metadata nor fixture outcomes can establish cash savings.

### D27: 2026-10-08, reject unbound fixture payload before upstream dispatch

A sandboxed probe of pinned agent-skill-eval 0.7.0 reproduced a mismatch:
`content_hash` excludes nested `evals`, `.git` and `__pycache__`, while `install`
copies those nested directories. Evidence and an unpublished issue draft are in
`reports/toolkit-v2/c04/nested-payload-probe`. No real answers or private files
were used. Keep the preferred evaluator; this finding does not justify silently
switching backends or calling its whole interface qualified.

The fixed development demo must accept only the two manifest-bound fixture files
and their parent directories. Reuse the bounded metadata reader, reject links,
extra files/directories and special files, then stage only captured hash-checked
bytes. This replaces the broad fixture-directory copy; it is not a general
candidate installer or an upstream patch. The source directory and existing
reports remain intact. Add finite negative tests and rerun the real fixed demo.

### D28: 2026-10-08, preserve failed setup state with existing helpers

The private development installer needs a record before effects and must check
space before creating parent directories. Reuse `component_setup.require_space`
and the existing compare-and-swap JSON writer. Keep standard venv/pip and the
same approved 24-wheel lock; add no package manager or installation service.
Record creating/bootstrapping/installing/installed/failed state, exact input hashes and target.
An existing or interrupted runtime remains protected from automatic retry.
Use an explicit public index, disabled pip configuration/cache/version checks and
a minimal environment so installation does not inherit provider credentials or
write the user's normal pip cache. The initial check used deterministic installer doubles for failures before and
after effects; the subsequent real replay is recorded below.
General extension policy, rollback and cross-platform qualification remain open.

The subsequent setup replay reused D19 authority for the same 24 pinned wheels,
private scope and finite fixture workload. No package, privilege, model, billing
or credential scope was added. After hash verification and the fixture run, only
the new unchanged temporary runtime was removed; the original runtime and wheel
cache remain. The runtime-free unit tests are not the evidence for this replay.
