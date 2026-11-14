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

### D29: 2026-10-09, connect selected manifests to reversible private installation

The operator directs continued implementation after the explicit finding that the
previous stop was premature. Reuse standard venv/pip, the existing space check,
file lock and compare-and-swap writer. Generalize installation to an explicitly
selected manifest closure and local hash-locked wheels; do not add a package
manager, Router configuration, remote installer or host activation. Bind the
review to the complete plan, destination, interpreter and wheel contents.

Retain durable failure state and refuse implicit retries. Since the destination
must originally be absent, uninstall compares its complete applied tree with the
current tree before removing only that owned runtime; edited or added entries
block removal. Preserve the journal after removal. Test drift, conflicting state,
space, interruption and offline replay under the standing finite-test delegation.
This authorizes engineering checks, not installation of new third-party packages.

### D30: 2026-10-09, test upstream scheduling through separate existing workers

Keep agent-skill-eval's scheduler and deterministic graders in its existing
sandboxed private runtime. A fixed fake-harness shim requests one trial over
bounded stdin/stdout. The trusted AEEP parent validates the current fixed case and
arm, reserves through AssessmentRepository before dispatch, and uses
ContainerExecutor with one fresh, network-disabled worker for each of four trials.
The coordinator receives no Docker socket, receipt store or authority interface.
Only the worker adapter and three hash-checked upstream Python modules are mounted;
case instructions and the optional fixed skill arrive transiently over stdin.

This finite engineering check reuses the installed image
`sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7`,
Docker `/usr/local/bin/docker`, local socket
`/Users/edwintse/.docker/run/docker.sock`, 256 MiB/one CPU/64 processes per worker,
zero model turns, zero paid calls and at most four 65-second reservations. There
is no image pull/build, new package or credential access. It uses an explicitly
synthetic operation ledger, not a new live allowance or reset of an existing
assessment grant. Record actual retained failures and source hashes. Successful
execution proves per-trial plumbing only; capable Codex workers, live conformance
and general candidate intake remain independent gates.

The first actual controlled fixture dispatched four separate containers and kept
four receipts/reservations; cleanup inspection found none remaining. Unit review
then exposed that ReceiptStore itself does not redact actions (Router normally
does). The bridge now saves a redacted decision explicitly and uses the existing
per-event persistence sink before dispatch. The first synthetic evidence remains
historical and is not upgraded to the repaired privacy/event behavior. Separate
worker-source staging from the coordinator's writable sandbox before the next run.

The approved 24-wheel closure was also replayed through the general C03 installer
using the retained local wheel cache. Install, idempotent verification and removal
of the unchanged runtime succeeded. The sibling journal is retained; the original
evaluator runtime and cache are untouched. Two missing metadata license labels
were resolved from license files inside the already pinned wheels, with hashes
recorded. Resource preview figures are conservative installation allowances and
archive sizes, not runtime measurements or savings.

### D31: 2026-10-09, bind the controlled fixture to existing comparison analysis

Use the existing AssessmentPlan/RecipeDefinition/BenchmarkCampaignReport and
`assessment.reporting.fit_report` for the next fixture report. Freeze expected
case/arm positions before dispatch, retain the existing 100-case qualification
and 20-pair resource thresholds, resolve each worker receipt and hash-check its
independently graded output, then export the C02 bundle and HTML/Markdown report.
The fixed two-case suite cannot qualify; synthetic model tokens, model duration
and billing remain unavailable. The typed holdout positions exercise the analysis
contract only and are not real held-out observations. No inference engine or new
acceptance threshold is introduced. General live campaign binding, cost/price
analysis and controlled Codex conformance remain open.

### D32: 2026-10-09, harden actual installation space and candidate payload identity

Installer review found that declared disk estimates could understate a wheel
closure. Derive the reservation from staged/expanded wheel bytes and allocation
rounding plus bootstrap headroom; declarations cannot reduce it. Preserve the
completed ordinary suite at f454a00 and the intentionally interrupted coverage
run, then verify the corrected source. Unsupported no-follow platforms must fail
explicitly; their POSIX installer tests are skipped rather than failing Windows CI.

The reproduced upstream candidate hash/copy mismatch also needs a general intake
boundary. Reuse the toolkit's bounded metadata reader and standard filesystem
operations to capture a local SKILL.md payload, excluding evals/Git/cache trees
from both hashing and staging. Reject links, special files, credentials, excessive
payloads and ambiguous paths. Stage captured bytes only, and expose a content-free
inspection through the existing CLI. No candidate code executes or host skill
installation occurs. This is a small adapter guard around the preferred upstream,
not another skill installer or evaluator. Finite checks remain delegated.

## D33 — Resolve existing accounting for descriptive cost reports

Reuse `aggregate_accounting` and `CashAccounting.actual_cash_cost` for receipt
amounts, currency checks, charge reconciliation and unavailable evidence. Add the
small cost-per-verified-success calculation to the existing toolkit reporting
module; do not add another billing service or statistical engine. Include failed
run costs and refuse ambiguous shared receipts/charges or missing retry receipts.

A supplied monthly/yearly fee is an explicitly sourced scenario, not an observed
charge or payment authorization. Its descriptive break-even uses cost per verified
success, requires complete matched accounting and no observed success regression,
and states the unchanged-workload assumption. No confidence-supported benefit or
real price verification follows from a JSON field or content hash. Existing
reviewed AEEP analysis retains statistical conclusions and assessment overhead.
This decision authorizes implementation tests, not paid calls or a new evaluator.

## D34 — Check wheel compatibility and dependencies before installer effects

The C03 audit found two gaps in `4ddf045`: platform strings were matched between
policy and manifests without checking wheel compatibility, and `--no-index`
alone did not prevent direct-URL dependencies. Keep C03 IN_PROGRESS until repaired
and verified. No unsafe URL wheel was installed during this work.

Reuse the already installed `packaging` 24.2 library for wheel tags, versions,
Python requirements and dependency markers. Do not write another resolver.
Check the complete supplied closure before creating runtime state, reject active
URL requirements and dependency extras, and pass `--no-deps` to pip. The reviewed
24-wheel evaluator closure passes the new read-only check. Private install preview
must refuse platforms where tag discovery would spawn a compatibility probe.
The intended support is macOS with an unambiguous version and glibc Linux;
Windows and musl private installation remain explicitly unsupported.

The source also needs case-insensitive archive collision and startup-hook checks
for macOS. Preserve failed-install journals and existing user-edit protection.
This is a corrective implementation decision, not permission for new third-party
installation, model calls or changes to the selected delivery architecture.

## D35 — Generalize the upstream offline adapter without adding a runner

Reuse the existing controlled ASE bridge for candidate payloads and bounded
reviewed suites. The development adapter implements the C02 evaluator interface;
ASE still schedules and grades, and existing AEEP reservations, container
execution, receipts and analysis retain their jobs. Candidate hashes and staged
bytes must agree in both the parent and worker, including bundled resources.

Keep candidate instructions uninterpreted in this scripted mode. A finite suite
has at most 16 unique cases, two arms, zero model turns and no network. Its explicit
review binds candidate/source metadata, suite, runtime, adapter source, image and
output location. Each engineering replay records its own incurred operations;
no existing live grant is replaced or reset. This scope does not authorize a
real Codex trial or general third-party code execution.

General task prompts and upstream transcripts remain transient. Output retention
is off by default and, when selected, belongs to the reviewed plan. Verification
must distinguish checking retained artifacts from resolving canonical grading
records without retained contents. The original fixed synthetic records remain
unchanged.

For C06, use deterministic file-edit fixtures that actually edit files and
preserve unrelated content. Independently check the resulting artifacts against
literal expected results. Do not rename a formatting prompt “complex” when the
fake harness ignores the requested work. The suite must remain prominently
synthetic and cannot establish real candidate value or capable-Codex conformance.

## D36 — Report stopped synthetic runs through existing analysis

A worker failure currently preserves its canonical receipt or unresolved
reservation but stops before generating the ordinary report. Extend the same
controlled reporting path to emit an explicitly incomplete result. Reuse
`fit_report`, the operation ledger and C02 records for observed trials; do not
add another recovery engine or retry an uncertain operation.

Keep unknown grades unknown, count missing expected positions, retain elapsed
charges and show unresolved operations separately. Bind the stopped result to
an immutable completion record before accepting it in the read-only verifier.
Invalid worker observations must not become exposure evidence. A failed partial
report must preserve the original failure and receipt store for inspection.

This is a finite zero-turn engineering amendment under the standing testing
assignment. It does not add model calls, install packages, change thresholds or
create an authorization blocker. The current draft remains outside the checkout
while the prior source revision finishes its full checks.

## D37 — Complete descriptive means and bind the reused implementation

The reporting contract requires mean differences as well as medians. Add matched
control/treatment means, their mean difference and a relative fraction only when
the measured control mean is positive. Use the same measured pairs in both arms;
missing observations and a zero denominator cannot become zero savings. Preserve
unknown confidence intervals until a reviewed analysis supplies them. Show the
source/version, verified-success delta and invocation counts in readable reports
as well as JSON. Render very large percentages without overflowing finite values.

Reuse `verification_source_digest` to bind the AEEP implementation used by the
controlled adapter, alongside its existing worker/engine source hashes. Also
bind the operator entry point and verifier. A changed implementation must require
a new preview review before any evaluation effect. These additions require no
new statistical framework, package or external service. Draft tests pass outside
the checkout while the preceding source revision finishes verification.

## D38 — Repair the existing offline native probe's template selection

The actual credential-free pair launched both pinned Codex workers but failed
in paired observations. `CHECK` now contains a `DOCX_PROBE` placeholder; the
standalone offline workbook probe omitted its substitution. The main managed
inspection path already substitutes it. A corrected copy sets it to `False`,
leaving worker policy and the workbook-only fixture unchanged.

That corrected copy passed the full existing probe: private input trees, canary
and external-answer exclusion, shared library versions, treatment-only candidate
presence, dependency execution, interruption and cleanup. Exact original failure,
corrected source, image/binary/configuration pins and results are under
`reports/toolkit-v2/c04/native-offline-recheck`. Four temporary workers across the
two attempts were removed. No model turn, sign-in, credential volume, network,
image pull or build was used. Integrate the one-line correction and retain both
results. This is partial unauthenticated command evidence, not full conformance.

## D39 — Emit the existing comparison contract from controlled reports

The controlled path already recomputes AEEP analysis and retains its canonical
inputs. Export the C02 `ComparisonReport` alongside that analysis, binding the
bundle, frozen plan and analysis references. Reuse those contracts and the
existing verifier; no new inference engine is needed. Synthetic runs remain
inconclusive about real value, and a run with no observed trial is not assessed.
The readable report must show this scope explicitly. Keep prior artifacts valid;
new exports require the additional canonical comparison record and digest check.

## D40 — Select the existing AEEP fallback for the first managed-model adapter

The pinned agent-skill-eval 0.7.0 Codex harness was exercised without running
Codex: empty events, a completion without usage, and partial usage all produced
zero output tokens. Its default command inherits the caller environment and
uses workspace-write, with no paired managed-worker binding. Exact parser and
command-builder observations are in `c04/codex-harness-contract`. These are
reproduced contract gaps, not an observed credential leak or a failed model call.

Keep the working upstream scripted adapter. Select the plan's explicit AEEP
BenchmarkRunner/AssessmentService fallback for the first managed-model adapter.
Those existing services already own pre-trial identity, boundary verification,
reservation, canonical events, grading and uncertain-operation recovery. A thin
adapter can expose their reviewed plans and evidence without duplicating those
controls in a second runner. This decision precedes any V2 live campaign; no
campaign has switched engines after a result. Revisit the upstream managed path
when an independently qualified shim or upstream change supplies these contracts.

The fallback must not copy grants or reset allowances. It can run only an existing
reviewed job through `AssessmentService.run`, preserve every canonical failure
and cost, and label missing normalization fields explicitly. Source association
must be reviewed before execution. It does not grant protected sign-in, model
spend, remote disclosure or automatic admission. No architecture choice is pending.

## D41 — Preserve missing fields in the existing App Server usage path

Follow-up review found a related legacy bug: `_token_usage` fills absent fields
with zero, then `turn_accounting` labels that record complete. Repair this before
qualifying the D40 fallback. Keep only supplied finite non-negative integers;
missing fields must produce partial authoritative evidence. The legacy resource
vector has numeric defaults, so preserve its wire contract and identify supplied
fields explicitly in sanitized receipt metadata. Toolkit normalization must use
that field list and evidence completeness, never treat compatibility defaults
as observations. Retain supplied counts. Use the existing partial-evidence contract, without rewriting old
records, widening worker access or adding a new accounting service. Exact source
pins distinguish the correction from historical receipts. Native conformance and
a live campaign remain required after implementation.

## D42 — Bind native normalization to recorded task instructions and discovery

Reuse `ManagedHostExecutor`'s rendered instruction and persist only its SHA-256.
This binds the shared task prompt without retaining task content or pretending
that a case-definition hash is the prompt. Candidate exposure remains a separate
observation. Preserve only `exposed`, `retrieved` and `invoked` boolean-or-unknown
fields when sanitizing discovery metadata; discard extra fields and payloads.
The existing benchmark already consumes those observations, but its receipt
filter previously removed the dictionary.

The optional D40 adapter reads canonical plans, campaign receipts and the full
operation ledger, then invokes the existing assessment service only after an
exact source/plan/implementation review. Candidate identity binds the complete
inspected dependency-hash map; the reviewed SKILL hash must occur in that map.
Missing identity, prompt or conformance references produce explicit normalization
gaps, while original costs and auxiliary-arm records remain authoritative. No
new storage, scheduler, grant, host launcher or statistical engine is introduced.
Draft code and tests currently live outside the checkout while D41's required
verification runs. They do not establish actual worker or live-model conformance.

## D43 — Show and reproduce the existing managed comparison analysis

Reuse `fit_report` for intervals, utility guardrails, challenger comparisons and
assessment costs. The first managed export saved those facts only in JSON;
connect them to the existing static renderer. Keep the canonical verdict separate
from the descriptive summary, and do not promote it to a new toolkit qualification
or release claim. No statistical engine, exporter dependency or service is added.

Reproduce the stored statistical fields, not just its verdict. Recompute costs
from the complete campaign and ledger, preserving the assessment service's
explicit missing-preparation-cost downgrade. Count expected trial positions from
the frozen suite and retain missing, unexpected and duplicate positions. Show
uncertainty, measurement coverage and unresolved operations alongside the result.
Use each case's existing template-family identity for normalized task slices.

The finite synthetic review adds altered-statistic/cost rejection, unknown-cost
preservation and readable-report checks. Draft code stays outside the checkout
until D42's source-bound full verification finishes. It authorizes no model call,
new software installation, credentials or release.

## D44 — Give both existing backends one explicit CLI entry point

Extend `aeep-toolkit` with `eval scripted` and `eval managed`; preserve their
existing plan/run/report arguments and direct entry points. The selected backend
is mandatory and never changes after failure. The managed path calls the existing
module; the scripted path invokes the fixed repository-owned bridge with the
current Python interpreter and argv only, keeping its imports in a separate
process. Neither path introduces a runner, scheduler or hosted service.

The scripted backend remains checkout-only until its development assets have a
reviewed distributable package. If those assets are absent, report unavailable;
do not silently substitute the managed backend or install anything. The plan
helper disables bytecode writes and retains the existing read-only preview.
Tests cover explicit selection, fixed argv, backend absence and propagated failure.

## D45 — Install AEEP's existing shared assets inside its private runtime

The real 0.8.2 wheel failed `check_wheel`: its 309 packaged documentation/example
assets use wheel data relocation, which the first private installer rejected.
The source-bound failure and archive sizes are in
`reports/toolkit-v2/c06/package-installation/pre-change-audit.json`. This is an
installer gap, not a permission or architecture blocker.

Keep standard venv/pip and preserve the legacy package contents. Permit only
`aeep_agent_router-VERSION.data/data/share/aeep/...` for the exactly reviewed
`aeep-agent-router` wheel and version. Pip places those files inside the new
private prefix. Other relocation schemes, distributions, versions, traversal,
startup hooks and links remain rejected. The existing whole-tree snapshot also
covers these assets, so a user edit prevents removal rather than being erased.

The finite fixture review covers real private installation/removal of a synthetic
AEEP-named wheel and rejection of other relocation paths. It introduces no new
installer, package manager or live execution. The dependency artifact review and
an actual complete package installation remain separate checks.

## D46 — Disclose unknown memory without inventing a requirement

Keep the preview's default block for unknown memory. Add one explicit operator
policy acknowledgment, `allow_unknown_memory`, bound into the exact installation
review when true. False is omitted from serialization to preserve existing review
hashes. This acknowledges uncertainty only; disk reserve, licenses, permissions,
artifact closure and execution authority remain separate requirements. Runtime
memory stays null until measured. No automatic installation is authorized.

## D47 — Reproduce analysis independent of input ordering

The retained synthetic probe in `reports/toolkit-v2/c05/analysis-reproduction`
reproduced different bootstrap bounds for identical cases and seed after reversing
case order. Sort case and family identities in the existing `paired_interval`
helper. Its callers, thresholds, resampling count and grouping stay unchanged.
Historical reports keep their original source bindings; this correction needs
fresh verification and cannot rewrite their results.

Preserve unknown condition-level break-even values from the existing service:
condition reports precede completion of the reporting operation, while the root
costs are finalized afterward. Require every reported numeric condition cost and
all statistical fields to reproduce. Synthetic regressions exercise that actual
cost-finalization sequence and reject altered numeric values. This finite test
amendment uses the standing assessment delegation; it performs no live trial.

## D48 — Prepare private portable summaries with existing report contracts

Reuse the existing EvidenceBundle summary and DeveloperIdentity contract. A local
`export-preview` can omit task labels, paths, host/model names, receipt references
and run identifiers while retaining separate cohort hashes and aggregate unknowns.
Content addressing proves byte identity only. The initial trust status remains
unverified; no hash, supplied source or owner assertion proves independent review.
Source/developer disclosure requires explicit selection and exact candidate binding.
A supplied donation link is not a mandatory plugin fee or payment instruction.

The prototype stays outside executable source during D47 validation. Four finite
synthetic tests cover minimization, deterministic hashes, cohort separation,
source mismatch and no network/process/write effects. Publication, authenticated
developer identity and public reproducibility remain separate gates. No new
hosting, attestation, identity or payment service is justified.

## D49 — Correct stale catalog wording without inferring installation

The static catalog still calls agent-skill-eval source-only despite its recorded
scripted dispatch, and describes the implemented managed bridge as merely a
candidate. The reviewed draft marks these integration scopes experimental, binds
the known upstream wheel hash, and retains unknown installed/enabled state. Other
unqualified external options remain blocked. Catalog metadata cannot activate an
extension or replace its exact installation review. Update the old all-blocked
fixture assertion when integrating; preserve the explicit unqualified native-host
and live-evidence limitations. The draft remains outside source during validation.

## D50 — Connect optional software through its existing interfaces

Reuse DiscoveryService and its canonical provenance store for explicit toolkit
search, without constructing Router. Reuse upstream machine-readable outputs for
scanner and additional evaluator imports; preserve raw artifact digests and
source pins, and keep external claims separate from independently verified
EvaluationRun receipts. An imported pass or no-findings result cannot qualify a
candidate. Do not import optional packages during ordinary toolkit startup.

Add only the adapter code needed for these boundaries. No second discovery,
scanner, evaluator, telemetry server or workflow engine is justified. Exact
upstream contract checks and synthetic hostile-input tests are routine delegated
definition work; they do not authorize executing those packages. Full regression
is deferred until integrated implementation, per the latest operator instruction.

## D51 — Ship the existing scripted bridge as package assets

Use the existing setuptools data-file layout and sysconfig data-root fallback
used by workbook/SkillsBench assets. Package the current bridge, lock, metadata
and fixed fixtures instead of adding another evaluator or requiring a checkout.
Resolve candidate source from the imported toolkit package, not a guessed src
directory. Installed assessment identity must hash the actual AEEP namespaces
and execution assets with a distinct installed-format prefix; it must never
return the SHA of an empty checkout. Preserve checkout digest meaning unchanged.
Installed and checkout conformance remain different and cannot be transferred.

Focused checks cover changed installed code/assets, missing assets, legacy
checkout identity, CLI fallback selection and packaged asset inventory. Actual
new-wheel installation and worker conformance still need their exact review.
The earlier 33-wheel review cannot validate this behavior.

## D52 — Keep the external graph engine inside an existing executor

C11 needs one real external workflow fixture, not another graph framework.
Provide an operator-owned JSON worker using LangGraph's StateGraph and conditional
edges. AEEP treats the entire dynamic graph as one bounded command, with the
existing executor's authority, timeout, accounting and receipt boundary. It does
not translate loops into an AEEP DAG or expose arbitrary import/code paths.
Only the finite text fixture is implemented; checkpoint persistence, generated
code, concurrent subagents, resumable graphs and provider tools are unsupported.
A real installed-library run awaits its exact private runtime review. Synthetic
API tests alone cannot satisfy external workflow conformance.

## D53 — Reuse OTLP and the existing MCP transport

Choose Langfuse's documented OTLP/HTTP JSON ingestion interface for optional
observability. Add a minimized receipt-to-OTLP preview to existing telemetry;
reuse existing HTTP execution/authority if an operator later configures an
export destination. No SDK/server/database or auto-export is required. Preserve
raw resource dimensions as AEEP attributes, not guessed GenAI or cash fields.
Receipt timestamps describe the recorded operation, never a reconstructed model
trace. Supplied receipts stay unverified. Export keys/destination/disclosure
approval are absent, so no remote call is authorized by the preview.

ToolHive exposes MCP endpoints already handled by MCPExecutor's Streamable HTTP
transport. Keep that adapter and exact executor review instead of adding a
second MCP client or provisioning daemon. ToolHive startup, images, identity,
network policy and removal need their own selected deployment review; endpoint
connectivity alone cannot establish MCP isolation or paired-agent conformance.
Phoenix is an alternative server under different license terms, not a second
mandatory telemetry stack. Neither exporter nor ToolHive is runtime-qualified.

## D54 — Review private wheel scripts without broad data relocation

Preparing the LangGraph closure failed before installation: jsonpointer 3.2.0
and jsonpatch 1.34 ship three ordinary CLI scripts in the wheel `scripts` scheme.
Retain the rejection evidence. Support this standard private-venv placement only
for a wheel's exact normalized distribution/version directory and a plain command
basename. Reject interpreter/pip/activation overrides, nested paths and collisions
between wheels or generated entry points. All other third-party data relocation
remains denied. The wheel hash and displayed command inventory bind the effect;
no script runs during preview or becomes a global command. Installation still
requires the exact reviewed closure, and removal retains snapshot protection.

## D55 — Verify actual Waza comparison semantics

The approved Waza artifact uses a platform-specific executable basename. Retain
the initial pre-execution rejection and routine fixture amendment. Actual mock
runs then exposed a wrong driver assumption: Waza deliberately exits one for
neutral or negative baseline comparisons. Pinned cmd_run.go confirms this.
Preserve the failed process receipt, require the exact neutral diagnostic and
all six raw outcomes, and normalize without a benefit claim. The importer also
now treats is_baseline as an outer comparison flag; the nested object is control.
V4 passed this contract and removed the private executable/workspace. No model
ran. The failed attempts remain evidence, not qualifying runs or refunded work.

## D57 — Preserve general output contracts at the Codex boundary

An actual text qualification and a separate one-call diagnostic found a response
schema rejection before any task answer. The recipe's general JSON Schema cannot
be sent unchanged through Codex's restricted structured-output interface.
Keep the existing adapter and add an explicit reviewed `output_schema_mode`:
`structured` remains the default; `prompt` sends the same schema as an instruction
and relies on the existing local validator. Artifact completion keeps its fixed
structured envelope. No schema converter, evaluator or retry mechanism is added.
Renew configuration/source-bound conformance and use a fresh plan and cases;
preserve the failed plans, costs, recipe, grader and thresholds. See the
[actual diagnosis](../../reports/toolkit-v2/c07/text-task-review/README.md).

The later historical `.json-local` profiles already avoided this provider limit
by setting executor `output_schema` to null and retaining a required local schema
validator. Those profiles and results remain valid for their original scope.
The new option keeps the public output contract in its normal field and makes
the provider transport choice explicit. Both paths reuse existing local validation;
neither changes the recipe or grader. The initial renewed profile was selected
from the older pre-workaround plan, which caused an avoidable failed turn.

## D58 — Retain exact approval while storage blocks execution

The operator approved inactive-fixture cleanup, the current wheel check and the
generated-tool training review. Record approval separately from their immutable
review documents. Completed cleanup and installation must not be replayed.
Training approval remains valid for the same artifacts; capacity is a separate
precondition. Do not lower the 50 GiB reserve, shrink the reviewed allowance to
fit available space, or remove backups and unrelated Docker resources under the
fixture-only cleanup scope. Record deleted allocation separately from reclaimed
free space. No execution architecture or upstream selection changes.

## D59 — Resume only verified preparation, then stop on host readiness failure

On October 19, storage was sufficient and production source still matched
`d2c406f`. The editing launch guard incorrectly required a fresh-campaign preview
with no prior operations after an already charged storage measurement. Keep the
conservative production preview unchanged. An exact operational successor may
accept only pinned, completed zero-model preparation, with the complete future
schedule plus lifecycle allowance fitting the current ledger. Existing trials,
uncertain operations and started jobs remain prohibited. The queued-job successor
binds the same unstarted job and changes no tasks, threshold, model or worker.

The restored candidate matches the frozen hash; its original temporary file was
missing. Retain a durable licensed copy and bind future subjects to durable
locations. Preserve both launch failures and their charges. After the first real
trial was rejected at host preflight, stop the campaign and do not replay it.
A separate zero-model probe isolated a failing `account/rateLimits/read` RPC.
Classify that failure before assuming quota exhaustion, requesting credentials or
changing architecture. A successor campaign needs a fresh plan and disjoint cases.
See [the resumption record](../../reports/toolkit-v2/integration-completion/resumption-20261019/README.md).

## D60 — Repair the task proxy's measured memory shortage

The exact existing proxy was OOM-killed under 128 MiB before accepting TCP.
A reviewed reversible change raises only its cap to 512 MiB with no swap.
Startup/health peak was 189,833,216 bytes; TCP/CONNECT/TLS and both worker
readiness checks then passed. Keep its image, network and access policy fixed.
Record this supporting-runtime footprint separately from candidate resources.
No new worker architecture or authentication access is needed. See
[the repair](../../reports/toolkit-v2/integration-completion/worker-readiness-repair-20261019/README.md).

## D61 — Inherit the passed output-mode profile, not the failed predecessor

Editing-profile preparation replaced D57's passed mappings with an older plan
and lost prompt output mode. Construct fresh task profiles from the passed
`plan_1eed14b65d3741bca8b92d99edfa63fe` mappings and assert prompt mode in both
arms before effects. Refresh their configuration-bound pair evidence and use
fresh disjoint case sets. Keep recipe, grader, model, candidate and thresholds
fixed. The production adapter already implements this mode; no new protocol or
default behavior is needed. Preserve both failed plans and their costs. Build
any reusable challenger only from the new frozen training inputs, before value
holdouts, and keep generated source inert until its exact execution review.

### D62 — Preserve the generated editing tool and its training limits

The candidate-absent builder's exact source passed 28 original training inputs
against an independent reference. Preserve the bytes and imperfect platform
scope: usage asks for Python 3.11, while the bounded validation used the existing
Python 3.13 image. The user approved source 3360c74f… and optional exposure, then
approved a directory-only packaging correction after COPY made it non-traversable.
The new images preserve their base layers and final configurations. Freeze both
image IDs, generated source/usage hashes and construction-input lineage before
value holdouts. Training success cannot establish efficacy or justify source edits.

### D63 — Bind native metric names without elevating provider claims

Before value holdouts, correct generic token identifiers to the existing
provider/model/channel-qualified ledger keys. Preserve declared dimensions,
thresholds and guardrails. Protocol counts are provider_report/self_asserted;
their presence cannot establish observed/verified usage. Retain the 46-call
partial campaign and all costs, then use fresh cases with the same approved
workers and tool. Complete the task-quality/wall-time comparison and separately
label raw reported tokens. Accept an inconclusive strict verdict rather than
relabel evidence or weaken policy.

### D64 — Finish the comparison and retain its inconclusive verdict

The four-arm study completed 564 valid runs, including 105/105 holdout successes
in each arm. Candidate time estimate 0.79% has corrected bounds -4.61% to +6.52%;
there is no confidence-supported 10% benefit or task-success gain. Trusted token
pairs are absent and candidate-specific discovery/use telemetry is unknown.
Retain the canonical INCONCLUSIVE result, all assigned cases and failed setup
costs. Do not relabel provider counts, remove guardrails or launch further studies
to obtain a positive verdict. C07 completion passes; admission/efficacy does not.
Use the actual report for the separate human exercise and local beta decision.

### D65 — Repair capture verification and retain positive native loading evidence

The operator reopened token and candidate-use telemetry after the completed study.
The 564 original journals are available, so audit their capture chain read-only
instead of spending model turns to recreate counts. Keep provider-report trust,
the frozen utility result and the original report unchanged. A separate supplement
records capture consistency and descriptive counts.

Reuse the existing Codex OTLP collector and execution journal. The new toolkit
helper checks those contracts and exports their evidence; it adds no collector,
framework or dependency. General OTLP backends cannot recover omitted past events
or attest OpenAI's internal meter. Preserve the bounded snapshot at the router,
bind positive skill injection to the reviewed candidate and journal, and label it
as instruction loading. Missing metrics cannot prove non-use; loading cannot prove
semantic use. A prospective collector run needs exact review of its changed worker
telemetry boundary before any new live check. No architecture choice is pending.

### D66 — Correct stale collector image bytes before any diagnostic turn

The operator approved the exact capture bundle. Its package and documentation
checks passed; the collector check stopped before Codex initialization. Both
approved images contain bb758886… while the reviewed-file guard requires the
current d551e2f4… collector. The read-only public image-file audit establishes
this mismatch. Do not weaken the guard, use the stale collector, request sign-in
without evidence, or replay the terminal inspection.

Prepare two COPY-only derived images with the already-reviewed collector. Bind
both Dockerfiles, parent IDs, collector bytes, resulting output IDs and fresh exact
definitions before running new conformance. Preserve the unused maximum four
public diagnostic turns and the explicit-to-optional capture gate. Source, binary,
dependencies, model, destination and old campaign remain fixed. The earlier bundle
explicitly excluded builds/replay, so the concrete repair requires new approval.
See [the repair review](../../reports/toolkit-v2/c07/capture-image-repair-20261020/README.md).
No application rewrite, new framework or repeated broad test cycle is warranted.

### D67 — Resolve local image parents by repository name and immutable digest

The approved COPY-only build failed because its bare sha256 parent was interpreted
as a Docker Hub repository name. Preserve that terminal attempt and registry
metadata failure; do not report its network traffic as zero or replay it. Use each
already-local repository name followed by the same @sha256 digest. Require local
resolution to the pinned ID and no ONBUILD instructions before either build.
The charged metadata check passed both guards. This does not prove a build or
collector result. The fresh reference-only amendment retains collector bytes,
dependencies, model and the unused maximum4 public diagnostic turns. Its predecessor
forbids automatic retries, so actual execution needs the exact amendment approval.
See [the amendment](../../reports/toolkit-v2/c07/capture-local-parent-20261021/README.md).

### D68 — Keep policy and metrics overrides in one CLI argument scope

The corrected images start, and sandbox commands cannot reach their collectors.
Effective disabled-feature verification nevertheless failed in both workers;
treatment inventory stayed unverified. Preserve the failed conformance and stop
before model diagnostics. The relay currently splits repeated -c options across
both sides of the app-server subcommand. Move telemetry options before the
subcommand, after the pinned policy options, while preserving forced no-log/no-trace
settings. Synthetic regression tests establish that launch contract, not actual
Codex parser semantics. Require fresh source-bound conformance before concluding
that this correction resolves the observed failure. No guard or threshold is
relaxed. New collector/wheel bytes require their own exact review after one
integrated verification cycle. See [the engineering record](../../reports/toolkit-v2/c07/capture-policy-repair-20261021/README.md).

### D69 — Preserve the terminal failures; propose existing local tags with ancestry checks

The approved current-source wheel passed16 offline installed checks; no source,
upstream pin or dependency correction is needed. The collector build failed before
image creation because BuildKit looked up an existing local repository@digest in
the registry. Docker inspect success alone did not prove BuildKit resolution.
The fresh amendment uses the same two parent IDs via their existing local tags,
checks them before and after building, and verifies inherited execution configuration
and the exact parent filesystem-layer prefix plus one COPY layer. Treat the build
as unverified until it runs. Do not infer a credential need or switch builders.
The same pinned docs checker needs a fresh exact attempt after its lint-only
blank-line failure. Keep the historical attempts and costs; no automatic retry.
[The exact two-action bundle](../../reports/toolkit-v2/c07/capture-local-tag-20261021/README.md)
requires explicit approval under its predecessors' no-retry rules. No new package
installation, full test cycle or original comparison replay is justified.

### D70 — Rebind diagnostic callbacks from the exact current case

The copied diagnostic changed input/expected but retained an old hashed callback
name. The model turn completed; grading could not run. Preserve that unknown task
outcome and its cost. Reuse extensions.grader_name to bind the sole callback, check
registration before enqueue, and retain any receipt before assertions. The exact
routine definition correction changes no source, fixture, grader or threshold.
The fresh two-turn pair passed independent grading and token-capture checks.

### D71 — Required skill input needs its own exact runtime evidence

The final typed-input positive probe changed runtime identity and correctly failed
its old optional-profile boundary before model dispatch. Its reservation stays
charged. Fresh model-free conformance using unchanged images now passes all11
probe groups and collector denial for the exact required identity. Keep optional
selection and forced loading distinct. The [one-turn positive check](../../reports/toolkit-v2/c07/capture-explicit-profile-20261021/README.md)
needs new explicit turn authority because the prior human cap4 is fully charged.
No source or software installation change is needed. Do not infer loading/use
from absent metrics or promote provider reports to independent measurements.

### D72 — Verify forced loading without rewriting optional value evidence

The exact operator-approved extra turn passed with a native `codex.skill.injected`
event bound to the reviewed skill, runtime, receipt and journal. Four actual model
capture chains now verify; three independent task grades pass and one earlier
callback failure stays ungraded. Preserve all five charged reservations, including
the preflight skip. No further model turn is needed for capture engineering.
Optional selection/use and provider-internal metering remain unknown. Keep the
original comparison INCONCLUSIVE and admission disabled.

### D73 — Record actual comprehension errors and measured CLI limits

The human answered all five questions. The first two describe the separate native
workbook journey; control discovery is incomplete. Preserve the verbatim response,
help context and scoring. A targeted follow-up after clarification is helped,
never an unaided replacement. Add a companion guide without changing the frozen
presented files. CLI calibration now measures 24 offline commands and shared-host
counters using existing monitoring. It does not establish production acceptance
or justify a retrospective passing budget. Recommend only bounded local
experimental handoff; release and production claims remain separate.

### D74 — Qualify the bounded Mac CLI with prospective budgets

Recommend the existing single-user foreground CLI with on-demand assessments,
not a new service/infrastructure. Propose 256 MiB CLI RSS and 1/2-second p95
intake/report targets before fresh inputs. Separate 30 local transactions from
an optional exact-reviewed 12-turn resource-only batch. Retain whole-host,
Docker VM, container and process measurements separately; no missing peak or
contaminated baseline can pass. Targets are recommendations until accepted/frozen.
Do not replay the old efficacy study or infer new model/install authority.

Point human controls at the existing assess cancel/status and private remove
interfaces. Cancellation stops subsequent trial scheduling, not in-flight effects.
The assisted check runs help only and preserves all earlier human responses.
No new core module, dependency, upstream pin or source behavior is required.

### D75 — Prioritize comparative usefulness and evidence-based selection

The operator clarified AEEP's purpose: evaluate, select and manage capabilities
by demonstrated task-specific value. Infrastructure qualification is separate.
D74's numeric resource targets are unaccepted hypotheses, not product requirements;
its stand-alone 30-command/12-turn campaign is superseded as the default next work.
Derive operational thresholds from representative task sizes, frequency, user
latency tolerance and actual whole-system observations. Preserve established
security/input guards, storage reserve, cash authority and frozen study limits.

Separate candidate value from AEEP selection value and management safety. The
existing live study is INCONCLUSIVE and disabled admission by design; it cannot
prove independent live selection quality. Current synthetic contract checks test
policy mechanics only. Prioritize representative real-task/grader mapping and
frozen comparisons with equivalent inventories, credible baselines, correct
abstention and decision overhead. No new service, dependency or core module is
justified. Negative and inconclusive outcomes remain valid; do not tune holdouts
or thresholds to obtain a positive result.

### D76 — Grade bounded repository behavior and evaluate selection separately

Extend the existing executable-recipe boundary with version 4. A submitted patch
can replace only existing reviewed text files. Each behavioral check executes in
a fresh offline `ContainerExecutor`; expected answers remain in the coordinator.
The protected callback compares observed JSON behavior, rather than accepting a
child's correctness verdict. Reuse canonical attempts, reservations, receipts,
independent grader validation and existing scientific/reporting code. Versions
1–3 retain their meanings. No new evaluator service or dependency is needed.

Use pinned repository maintenance examples to develop the grader: the known CLI
option regression, actual token accounting with a seeded caller fault, and a
working callback contract. They are extracted development tasks, not independent
holdouts or evidence of model usefulness. Require curated 8/28/105 splits for an
assessment export; reject repeated origins and development-exposed holdouts.

Score policy decisions in a separate complete matrix with identical inventory,
model, environment and authority. Distinguish useful choices, ineligible or
unnecessary choices, missed applicable value, abstention and unknown value.
Preserve independent task grades and decision-time coverage. The importer does
not authenticate evidence and cannot admit a capability. Infrastructure budgets
remain separate. Source verification is in progress; contained checks and a
current-wheel installation need a fresh exact execution review.

## D77 — Preserve minimized receipts and adapter-owned validation

The first approved repository-grader review failed because its audit expected
container image/name fields that stored receipts deliberately omit. Keep that
privacy contract. Bind the receipt to its canonical completed attempt, executor
fingerprint and terminal receipt list; derive the owned container name from the
attempt ID. Treat the image as a reviewed environment binding, rather than claim
it was observed in omitted receipt metadata. Keep the failed attempt and charges.

Move versioned catalog-envelope validation behind the existing managed-host
registry. Core routing calls that boundary; the registry recognizes the built-in
Codex v1 envelope and delegates field validation to the existing validator. Unknown
schemas and malformed observations still fail closed. No validator, measurement,
receipt schema, optional-candidate policy or dependency version changes.

The six audit regressions, both 1623-test full runs and all 13 integrated source
checks pass. Fresh exact contained execution remains pending approval. The source-bound
first-party lifecycle fixture passed admission/use, revocation, stale rejection
and baseline selection; it supplies no real-plugin benefit or live policy-value
claim. Evidence: `reports/toolkit-v2/c13/repository-audit-correction-20261021/`.

### D78 — Reuse upstream repository tests before new model comparisons

The approved correction bundle passed on source5f4e318c. Its bounded callable
fixtures are development conformance, not a full-repository workload. Keep the
existing managed fallback, assessment service, runner, controlled executors and
receipts. Add a benchmark pack rather than another evaluator service.

Use the pinned, CC-BY-4.0 SWE-rebench leaderboard pool as a candidate source.
The union contains 860 unique issue IDs from 413 repositories; none is adopted
yet. Review underlying repository rights and exact runtime closures. Shared
origins and absent preservation tests remain exclusions to resolve. Do not infer
independence, clean model exposure or chronological freshness from dataset labels.
The documented SWE-bench Verified contamination/test-quality concern prevents
using it as the default without a task-specific validity argument.

First test the MIT-licensed upstream pytest parser/resolution functions against
one real Loguru issue and its upstream tests in the existing pinned image.
Seven exact cached wheels and a pytest8.3.5 runtime adaptation fit the current
transport; this is not official-image equivalence. All inspected development
tasks stay outside future holdouts. Six static preparation checks pass. Exact
six-call execution review56ca1751 is pending approval; the previous terminal
approval does not cover this external code. No architecture change is needed.

Follow `reports/toolkit-v2/c13/repository-cohort-20261022/WORKLOAD_PLAN.md`.
Complete the real repository pack, curate reproducible stage-disjoint cohorts
and freeze all mappings and thresholds before new model calls. Comparative
usefulness precedes selection labels. An inconclusive capability is not proven
useless, and abstention alone is not selection benefit. Resource acceptance
remains a separate workload-derived question. No threshold or grant counter
changes. Preserve historical results and prospective token/use unknowns.

### D79 — Curated repository suites reuse artifact delivery and protected grading

The exact six-call upstream check56ca1751 passed on source5f4e318c. Its real
Loguru baseline, published repair and preservation regression behaved as expected.
That result justifies reusing pinned upstream pytest parsing and real test suites;
it does not qualify a candidate or the new integration.

Version5 adds hash-bound coordinator assets and small curated case records to the
existing executable-recipe boundary. Existing managed-host artifacts deliver one
public source archive and return a patch file. The protected coordinator checks
base/scope and compares raw contained test observations with required test IDs.
No new host protocol, runner, database, installer or required dependency is added.
The MIT upstream parser/enum bodies, license and provenance are bundled explicitly.

Curated generation and published-reference lookup are data operations on the
existing ledger, not additional executable engines. The legacy extension slots
remain serialized but are not dispatched for those v5 roles. Existing8/28/105,
current-runtime checks, replay barriers, scoped semantic-fault validation and
scientific thresholds remain binding. Origin declarations default to synthetic
and do not authenticate source or independence. Transport/input safety bounds
are not production resource acceptance budgets.

The first34 focused software tests pass and targeted branch-aware coverage of
the new module is96%. Full configured verification is running on source573257b2.
Fresh external v5 conformance, installed-wheel checks and licensed independent
cohorts remain open. No model study, installation, credential, release or larger
spending permission follows from this source implementation decision.

### D80 — Separate v5 conformance from corpus and capability evidence

Corrected source `fcd91dde` passes all thirteen configured source checks, both
coverage gates and the retained proof/Node checks. A real-process regression
checks `src/` import precedence. The earlier source run stopped at its drift guard
and remains incomplete. No old execution result transfers to the changed pack.

Use three real development issues to check v5 before adopting a cohort: Loguru,
Click and Marshmallow. Their licenses, exact source revisions, pure wheel bytes,
private test overlays and published source repairs are reviewed. All three are
single-file repairs. Explicit source-only scope omits published documentation
changes, and Marshmallow's Python3.11-to3.13 adaptation remains visible. Preserve
all four inspected development repositories outside later stages.

The new exact bundle binds twelve contained calls, the actual changed wheel and
the cached offline documentation checker. It awaits its own execution approval;
no model, credential, spending or architecture decision follows from source tests.
Continue with licensed reproducible cohorts, then required-use qualification and
optional-use comparison. Selection labels require actual independent value
results. Metadata candidates, working reference repairs and resource adequacy
cannot supply those results. Existing frozen thresholds and counters stay intact.

### D81 — Preserve failed attempts and replace only the uncertified fault datum

Actual approvals a2787cd8 and6174f3e4 were exercised once. The changed wheel's
nineteen private installed checks and the pinned offline docs check passed.
All three real repairs pass their912 required identities; originals fail11 bug
identities and preserve901. These development results establish no model benefit.

The first review script mishandled a rejected fault's pytest exit4. A pure audit
regression checks its correction. The next attempt's final import-fault reply
failed protocol validation before raw reply retention. Preserve both terminal
failures and all16 operation charges. The second malformed field and its grade
remain unknown; a later result cannot repair that history.

Review89245763 changes only the deliberate Marshmallow counterexample and its
report driver. A leading return bypasses URL validation while keeping imports
intact. Require all190 test identities, five bug tests still passed, at least one
preservation failure and a valid invalid/test_failure result. Retain its bounded
public-test reply before validation. No product, observer, dependency, positive
case, permission ceiling or utility threshold changes. This is development data,
not a frozen holdout revision. One fresh exact approval is required; no completed
call, wheel check or docs binary is replayed.

### D82 — Finish development conformance, then reproduce independent workloads

Actual approval `89245763` completed the remaining semantic-fault check. All190
required identities were observed, five repaired bug tests stayed passed and 68
preservation tests failed. AEEP rejected the bypass as invalid/test_failure.
The raw reply, canonical receipt and completed attempt are retained. Across the
three approved attempts all 13 physical receipts were reopened and owned containers
were absent. Preserve both earlier terminal failures and the lost reply as unknown.

Continue with eight provisional cases from different repositories, excluding
all four development repositories. Six use published source repairs; two are
authored correct-snapshot audits with explicit byte-preservation contracts.
Retain the real issue/test/repair provenance and source licenses. Their current
4/2/2 family mix is a curation batch, not a balanced final screening stage.

Review `4cfc412d` binds at most 16 offline reference/counterexample calls, 18
operations and 710 reserved seconds. Reuse the exact source, observer, runtime,
image and containment evidence. Do not reinstall the passed wheel or repeat docs
execution. A nonreproducible case is recorded and excluded; independent cases
continue after verified accounting and cleanup. Common authority, identity or
lifecycle uncertainty stops dispatch. New third-party execution awaits its exact
approval. No model, corpus adoption, value label, selection claim or resource
acceptance follows from static preparation or reference reproduction.

### D83 : preserve workload exclusions; fix explicit plugin support

Approved batch4cfc412d completed fourteen calls and sixteen canonical operations.
Six cases reproduced, two references failed and their negatives were skipped.
All fourteen completed attempts/receipts were reopened and containers absent.
Charges are24.288069125264883 seconds, zero models and cash; sourcefcd91dde was
unchanged. Exact results are in the screening-curation completion audit.

Files-to-prompt has an incompatible Click test option; Jsonpickle requires absent
Ruff plugin identities. Preserve both exclusions and frozen test sets. No retry
or positive value/selection claim follows. Later review48fa60c0 is withdrawn
before execution: Py3status's three changed Python files include two docstring-only
changes. Metadata file counts do not verify multi-file complexity. The source-body
AST audit and withdrawal are retained in repository-workload-expansion-20261022.

The next genuine multi-file candidate needs pytest-mock, while the current
observer disables autoload and cannot declare a reviewed plugin. Add explicit,
versioned plugin support to the existing protected grader, preserve v1 meanings
and observer bytes, then verify changed source and prepare a corrected exact
runtime review. Full independent cohorts, model qualification, usefulness and
selection remain unproven. Human controls, resource acceptance and release remain
separate; no new third-party execution or installation is authorized.

### D84 — Explicit plugins verified; correct family evidence before freezing

Source `f694024c` adds version2 explicit pytest plugin declarations on the existing
grader. Legacy case, recipe, truth-schema and observer digests remain identical.
All13 configured source checks pass on unchanged bytes:1673 tests in each full
run,21 skips,82% total coverage and both branch gates. Fifty focused contract
tests pass. This proves the software contract, not external plugin conformance.

The late actual approval of48fa60c0 is recorded but unused: its bundle was already
withdrawn and binds old source and an invalid multi-file premise. No image,
installation or contained call ran under it. The broader source-body AST audit
also found that Dissect.cstruct and Mockito each change only one executable file.
Their real test results remain valid; their earlier multi-file labels do not.

Prepare one corrected finite runtime, wheel and docs review. Use genuine
multi-file source changes and check the second behavior where upstream selected
tests alone omit it. Retain authored-test provenance and unchanged upstream
assertions. Do not adopt a balanced cohort until source and runtime checks support
it. No model, value label, resource acceptance or release follows from this work.

### D85 — Keep whole-module failure; declare the intended test subset explicitly

Review038b2af9 built the optional25-wheel image and passed its three fresh probes.
Seven cases reproduced. Leanclient's14 required identities passed, while three
additional Lean-server fixture tests errored. Its whole-module exit1 remains
failed; the exact tracebacks remain unknown. Do not relax global exit,missing,
error or preservation guards to call that observation passed.

Prepare a new publicly scoped diagnostic-range task with all14 existing required
identities/assertions. An appended protected conftest hook selects those exact
nodes. Source,observer,image,permissions and product code stay unchanged. First-party
collection fixtures and synthetic guard checks pass; actual execution remains
separate. Review7bbc9678 covers four fresh observations only. No reinstall,docs
rerun or image build is needed. This is an unfrozen task adaptation,not a change
to a frozen holdout or utility threshold. Keep the old failed task and all charges.

### D86 — Complete the declared-test check; retain the failed whole-module scope

Actual approval7bbc9678 ran once on unchanged sourcef694024c. Each of four
observations contained exactly the14 required identities. The reference passed;
original source and both per-file partial repairs were rejected. All four
canonical attempts/receipts were reopened and owned containers were absent.
Six operations charged8.131443957798183 seconds. Current grant counters are12886
operations,3744 turns,118281.42178913252 seconds and0.0 cash. No model turn or
cash was used. The old whole-module failure remains failed; its exact exception
remains unknown.

The copied launcher and auditor had a stale parent-directory index. Before any
reservation, a recorded amendment under standing finite-definition authority
bound their ROOT global to the already authorized repository. Reviewed module
bytes, checks, source, image and ceilings stayed unchanged. There was no erroneous
dispatch and no second execution attempt. The completed review cannot replay.

The composed record is
`reports/toolkit-v2/c13/repository-declared-tests-20261022/composed-screening-reproduction.json`.
Eight provisional screening cases now reproduce, with3/3/2 families,234 required
reference identities and six per-file partial-repair rejections. Across both
reviews,26 physical receipts were reopened; build and calls charged31 operations
and55.99806087464094 seconds. No full8/28/105 stages are frozen or adopted.
Next work is independent training/holdout curation and runtime reproduction,
followed by fresh applicable worker qualification and optional-use comparisons.
Current source,installed wheel19 checks and offline docs69 need no repeat.
Human controls, resource acceptance, selection outcomes and release remain open.

### D87 — Keep original exclusions; adapt runtime truth without replay

Actual approvalab120327 ran once on sourcef694024c and the existing image. Six
cases reproduced under its frozen expectations. Nineteen physical calls completed;
all canonical attempts/receipts were reopened and containers absent. Twenty-one
operations charged42.763097875751555 seconds. Counters are12907 operations,3744
turns,118324.18488700828 seconds and0.0 cash. Skipped slots remain unused and the
review cannot replay. No model or cash delta; source/package/docs need no rerun.

A separate standing-authority Python3.13 truth adaptation retains all422 Beniget
assertions. Three newer-builtin tests already pass on original source and become
preservation checks; three WindowsError tests remain fail-to-pass. Both physical
payload hashes equal the completed reference/original calls. Local first-party
regrading passes without external execution. The old exact classifier outcome
remains failed. Circuitbreaker,Param and Python-json-logger remain excluded;
raw replies retain statuses but no detailed exceptions, so exact causes are unknown.

The current provisional pool is15 cases,including the earlier eight screening
candidates. The seven new tasks contribute4 single-file repairs,1 genuine multi-file
repair and2 authored audits,653 required reference identities and2 new per-file
regression rejections. No full8/28/105 stages are frozen or adopted. Independent
cohort curation, fresh applicable model-worker qualification, optional-use value
and independent selection remain the critical path; resource acceptance is separate.

Static source review covered49 issues from31 repositories and identified a second
false multi-file label from attribute documentation strings. Original audits and
failed inert drafts remain retained. Git-blob source scopes preserve selected code,
licenses and assertions with exact omissions. A real SQL repair's whole-file JSON
reference exceeds current artifact bounds despite a3700-byte published diff;
transport-limit-finding.json records a proposed compact-patch direction,not savings.
Evidence: reports/toolkit-v2/c13/repository-corpus-expansion-20261022/.

### D88 — Use bounded gzip for larger patches; preserve prior contracts

Version3 adds explicit bounded gzip-JSON replacement-file artifacts. Standard-library
gzip handles the transport; no new parser,executable,dependency or service. Legacy
v1/v2 case records,truth schemas,recipe IDs/digests and observers compare identically.
The real three-file SQL reference is774091 raw JSON bytes and147888 compressed
bytes. This is an artifact measurement,not token,time,memory or monetary savings.
V3 decoded JSON uses the existing4000000-byte source-tree bound. Existing archive,
member,payload,edit-scope and correctness guards remain; old patch limits stay fixed.

Source59b9d61c passed all13 configured commands without drift:1676 tests in each
full run,21 skips,the existing Starlette warning,82% total coverage,both branch
gates,Ruff,layering,mypy and builds. Fifty-three focused tests and exact legacy
serialization proofs pass. Full session5348 is terminal; do not repeat it.
Offline docs lint passed69 files. Source/wheel/runtime proofs for f694024c remain
historical; current installed/runtime checks have not executed.

An extra CI proof exposed a pre-existing stale test-file index binding from C07.
All executable checks passed. Refreshing that one offline binding passed the
current proof; the old lock and failed report are retained. No live or release
gate follows. DSH's optional Node runtime check cannot import
@deepseek-ai/dsh-llm;12 other Node tests pass. No npm installation occurred.

Five compact cases and19 inert observations are prepared. Reviewae4ab2f0 requires
three fresh source-bound probes before subject calls:at most22 offline calls,
24 existing-grant operations and920 reserved seconds on the same pinned image.
Sixty-two assets,22 classifier checks and25 first-party grader guards pass.
No external source execution,install,image change,model turn or cash occurred
in this source work. Exact combined runtime/current-wheel/docs authority is being
prepared. Full8/28/105 stages,value,selection,human controls,resource acceptance
and release remain separate. Latest canonical grant remains12907 operations,
3744 turns,118324.18488700828 seconds and0.0 cash.

### D89 — Retain four reproduced compact cases and one exclusion

Actual approval31c5138d executed the compact bundle once on source59b9d61c.
Four cases reproduced: SQLglot4643,5256,6374 and Circuitbreaker67. Seven SQL
per-file regressions were rejected. SQLglot7479 reference exited2 with a collection
ERROR and missing required identities; detailed exceptions were not retained.
It stays excluded and its three later variants were not dispatched. This isolated
failure did not prevent the installed wheel19 checks and offline docs from passing.
Both private runtimes and package scratch were removed after unchanged checks.

Nineteen physical attempts/receipts were reopened and all owned containers were
absent. Twenty-one operations charged47.338871458079666 seconds. Grant counters
are12928 operations,3744 turns,118371.52375846636 seconds and0.0 cash. Three fresh
source-bound containment/state/runtime probes passed. No model or cash delta;
no broad source,package or docs rerun is needed on unchanged artifacts.

The consolidated pool has18 distinct snapshots from16 repositories:8 single-file,
6 multi-file and4 authored audits,975 required reference identities. SQL5256 is
counted once using its newly reproduced v3 record. Four records carry current
source59b9d61c;14 retain earlier bindings. No conformance transfers to those records.
No full8/28/105 stages are frozen or adopted. Qualification, optional-use value,
independent selection, human controls, resource acceptance and release remain open.
Next work expands the corpus with one finite runtime review; it needs no architecture
choice or package/docs repeat. Evidence: reports/toolkit-v2/c13/repository-compact-patches-20261022/.

### D90 — Review one finite runtime expansion for a larger task batch

The approved compact bundle is committed as159958c. Current source59b9d61c,
installed wheel19 checks and offline docs are verified; do not repeat them.
The new review38f87c22d21c564aa35dd9b9a05efec6657dd658bfddfe6ee3e74fcfbb35d3de
prepares22 distinct snapshots from six repositories:3 single-file repairs,
17 multi-file repairs and2 authored audits,1572 required identities and94 variants.
SQLglot supplies15 snapshots and remains one repository group across stages.
No case has run on the proposed image and no stage is frozen or adopted.

One private image would install14 exact official wheels over retained image027b7b37.
The static closure,110 first-party grader guards,22 classifier checks,280 asset
bindings and JSON-only deterministic derivation fixture pass. No new core service
or mandatory dependency was added. The proposed maximum is one offline build,
97 calls including three fresh probes,100 existing-grant operations and3240 reserved
seconds. No models,downloads,pulls,credentials,cash,package/docs reruns,activation,
release or old-image deletion. Actual user approval is required for this new
untrusted installation/execution; no architecture choice is needed.

The unapproved0976c301 draft is withdrawn before execution: static review caught
DjangoBird's automatic xdist workers. Its new pytest.ini keeps original Python
source,assertions and other settings while selecting serial execution. SVCS now
retains its base CHANGELOG for inert patch application. SQL5253 source collection
failed DNS and is excluded. Smaller initial preparation failures and all drafts
remain. The old SQL7479 collection failure is unchanged; pytz is a static missing
runtime import to test,not a recovered exception. No grant charge occurred here.

Capacity remains explicit:18 reproduced candidates plus22 unexecuted proposals.
Even if all22 pass,101 more distinct cases are needed for the balanced8/28/105 stages.
Do not infer completeness,usefulness,selection quality or savings from reference
reproduction. The current grant remains12928 operations,3744 model turns,
118371.52375846636 seconds and0.0 cash. Human control discovery,optional DSH dependency
conformance,resource acceptance and release remain separate.
Evidence: reports/toolkit-v2/c13/repository-workload-batch-20261022/.

### D91 — Preserve seven exclusions and recover two historical single-file cases

Actual approval38f87c22 ran once. The offline14-wheel image build passed and is
retained as aeep-toolkit-v2/repository-grader:py313-pydantic-django-20261022,
IDsha256:324a1fee6ee58475ecfdc659c98be5b5a8480fae4389b26b13b5b0b43bc32d2b.
Inherited execution configuration/parent layers are unchanged; growth19695260 bytes
passed the operation cap. All three fresh containment/state/runtime probes passed.
Fifteen of22 tasks reproduced under the frozen expectations. Eighty-four physical
attempts/receipts were reopened and all owned containers are absent; the owned
nonsecret canary was removed. Build/setup/analysis/calls charged87 operations and
211.08177674980834 seconds. Grant counters are13015 operations,3744 turns,
118582.60553521616 seconds and0.0 cash. No model or cash delta; no automatic replay.

Seven exclusions are explicit in exclusions.json. DjangoBird has truncated upstream
parameter IDs:21/59 required identities were observed,not59 passes. Dishka requests
an unprovided coverage plugin in .pytest.ini. Prometheus's benchmark-fixture test
errors while its authored preservation guard passes. Two SQL cases accept an
incomplete repair; one partial fails at import with missing tests; another original
status map differs from metadata. SQL7479's reference now passes with pytz,but its
per-file regression still fails the acceptance criterion. Detailed pytest exception
text is unavailable; static configuration explanations are labeled as inferences.
No assertion,count or criterion was weakened to retain a task.

Two earlier Dissect.cstruct/Mockito cases were recovered as single-file repairs
under standing definition authority. AST inspection confirms one executable body
change in each; both original replacement files remain. All four physical payload
hashes equal completed historical observations. Four canonical receipts/attempts
were reopened and containers absent. Local first-party regrading passes without
external calls,models or new canonical operations. Old labels and runtime bindings
remain; no current conformance transfers to those old records.

The pool now has35 distinct snapshots from20 repositories:12 single-file repairs,
18 multi-file repairs and5 authored audits,2257 required reference identities.
Full balanced8/28/105 stages still need106 additional cases and are not frozen or
adopted. Source59b9d61c,its13-command verification,the installed wheel19 checks and
offline docs remain unchanged; do not repeat them. The next integration check should
exercise the repository artifact journey with the real model on the three already
excluded development repositories,using optional candidate access and protected
independent grading. Prepare a small exact execution review with fresh worker
conformance. It cannot replace100-holdout qualification or the full usefulness/
selection gates. Continue independent corpus work; no architecture change is needed.

### D92 — Correct prospective reservation math before another execution

A post-execution budget audit found a preview defect in38f87c22: the full bound
used30 seconds per grader call instead of invoke's35-second reservation including
its wrapper margin. The correct full97-call cap sum is3725 seconds; the review says
3240. The87 executed operations' individual caps sum to3270. Preserve this mismatch
and the immutable review. Actual charged time is211.08177674980834 seconds,with every
operation completed within its individual cap. Counting all four maximum stage
reservations simultaneously plus every final charge gives a conservative upper
bound below3240,so no observed outstanding/charged balance exceeded that budget.
This does not make the prospective preview correct. No usage counter or historical
record was changed. Before further execution,compute timeout+5 bounds and enforce
the exact review ceilings on every reservation. The evidence is
repository-workload-batch-20261022/reservation-preview-correction.json.

### D93 — Exercise the real repository path before further corpus expansion

Prepare a six-turn development comparison on Loguru,Click and Marshmallow,using
ordinary capable workers and optional Ponytail4.10.0. Reuse AssessmentService,
BenchmarkRunner,the existing artifact transport,protected graders,collector and
images. New core services and repeated unchanged package/source checks are not
needed. All three repositories remain excluded from future holdouts.

Review9f0bf880 binds184 assets and limits execution to6 turns,128 operations,
10000 reserved seconds and0 cash. Fresh current-source worker/collector checks
and independent grader validation precede tasks. The driver checks the exact
review ceiling before every reservation,including timeout+5 margins. Preparation
checked six archive bindings and seven guard cases without external execution.
Actual exact approval remains necessary for untrusted execution and disclosure
of these pinned public tasks to the existing destination. Routine deterministic
definition compilation remains delegated. No architecture decision is needed.

This is development engineering evidence,not a timing pilot,formal qualification,
full usefulness study,selection validation or admission. Task errors remain errors;
optional loading and missing metrics remain explicit. Three pairs cannot establish
a material benefit. Keep the35-case provisional corpus and all historical failed
observations independent. See repository-model-journey-20261022/README.md.

### D94 — Carry accepted counterexamples into the compiled recipe

The actual approval9f0bf880 ran once. Both workers passed11 observed conformance
checks and collector denial. Normal grader validation stopped after nine contained
calls,before models. I carried the obsolete Marshmallow import-time fault into the
compiled recipe instead of its earlier accepted semantic replacement. All nine
payload action digests match first-party reconstruction in order; the last call
is that old fault. Its exact malformed reply field is unknown because the reply
was not retained. This failure is not model performance or a valid task grade.

The terminal audit reopened nine canonical receipts/COMPLETED attempts,verified
owned grader absence and the stopped proxy,and reconciled all15 complete canonical
operations with65.09651541616768 charged seconds. Grant counters are13030operations,
3744turns,118647.70205063233seconds and0cash. Source59b9d61c is unchanged. No model,
image,installer,credential or cash effect occurred. Preserve the failed result and
all charges;unused model slots do not authorize replay.

Correction reviewd775e93e binds195 assets and the same6-turn/128-operation/10000-
reserved-second/0cash ceiling. It substitutes the exact URL-validator fault source
already certified in89245763,through the existing gzip encoding. Patched archive,
public inputs,protected tests and reference files match the certified record.
A first-party historical-status replay confirms invalid/test_failure,all190 test
identities,five passed bug tests and preservation failures;it is not new runtime
conformance. Both worker fingerprints and actual fresh boundaries are unchanged,
so reuse them. Normal independent grader validation still precedes all models.

The corrected typed recipe was stored under standing definition authority without
counter changes. Seven reservation guards,two bounded observer filters,driver
syntax and195 asset hashes passed. The corrected driver reuses the existing runner
and retains declared bounded public observer fields before validation,excluding
raw model/source/artifact/authentication data. No product source changed;do not
repeat full source,wheel,docs or worker checks merely for this protected-fault fix.

The remaining intervention is this exact execution approval because9f0bf880
explicitly forbids automatic retry and the pasted continuation withholds general
untrusted execution authority. No architecture decision is needed. See
reports/toolkit-v2/c13/repository-model-fault-correction-20261023/README.md.

The completed first-party full validation replay exercised validate_grader with
retained historical observer replies:3 literal fixtures,15 replayed calls and48
rejected faults across57 decisions. No external code,worker,model or canonical
grant operation was executed. This confirms corrected definition wiring only;
current runtime validation remains pending exact approval. All195 pending-review
assets are unchanged. See repository-model-fault-correction-20261023/grader-replay-check.json.

### D95 — Verify rendered case delivery and stop on the first uncertain invocation

Approvedd775e93e ran once on source59b9d61c. All15 independent grader validation
calls passed and their bounded public replies are retained. The model phase
then made five actual turns with indeterminate invocation failures and no external
task grades. The coordinator requested supported cancellation after observing
three failures;five turns were already dispatched/completed before it took effect.
No sixth turn ran. All29 operations are complete and313.0355685814284 seconds remain
charged. Grant13059operations,3749turns,118960.73761921376seconds,0cash. Owned grader
containers and both reviewed worker images are absent from running/stopped
containers;the existing proxy is stopped. No image,volume or backup was deleted.

The audit proves the prepared instruction was constant across cases and omitted
actual task text,base hash,editable paths and artifact paths. The archive transfer
did not supply that missing task contract. This is a preparation defect,not an
incorrect agent answer. Receipt metadata also filtered out cleanup confirmation
and artifact hash/size. The exact original failure cause remains sanitized and
unknown. Five token chains are partial with all five categories and provider_report/
self_asserted provenance. Two treatment turns positively observed implicit Ponytail
instruction loading;that supplies no task usefulness or selection evidence.

Source78bf89bd repairs immediate stopping after an indeterminate trial,preserves
safe cleanup/artifact metadata,and retains bounded artifact/cleanup failure codes.
The39 targeted regressions passed with3 skips;Ruff,policy and mypy passed. Required
full source/coverage verification is running in repository-task-delivery-20261023.
Its product bytes are frozen until that run finishes. Old source59b9 runtime,wheel
and worker records retain their original meanings;they do not qualify source78bf.

New inert worker definitions append the existing{input} template. Six checks
through the actual ManagedHostExecutor with a recording stub verify public task,
base hash,editable paths and artifact paths,exclude archive/oracle bytes,and show
three distinct case instruction hashes with equal control/treatment text. This
is preparation evidence,not worker conformance. A separate five-case synthetic
check reads external grades from bound canonical BenchmarkTrial.case_validation,
rather than the earlier execution receipt's unknown task_valid. No model or grant
operation was added by these first-party checks. Full usefulness/selection remains
open;do not replay terminald775e93e or infer savings from these failures.

### D96 — Keep fixture frame limits separate from production and preserve strict stops

The initial full run on78bf89bd completed1677 passed/21 skipped/1 failed. Read-only
inspection traced the identity/admission fixture's first stopped invocation to a
valid1155-byte CSV output exceeding managed_config's1024-byte protocol-fixture
limit. The fixture now uses16384 bytes;its focused identity test passed in36.66s.
No production frame limit or campaign threshold changed. The strict first-uncertain-
trial stop remains. Safe artifact fields now reject nonboolean cleanup flags,
non-SHA256 strings and noninteger/out-of-range byte counts. Forty focused tests
passed with3 skips;Ruff and mypy passed. Source4cb0bf74 is frozen for final full
verification in session94490,validation-final;do not restart that run.

The new source4cb0bf74 inert definitions,requests and six rendered task checks
replace only unexecuted source78 prototypes,which are retained in draft-source78.
Actual failed models still bind source59b9. New conformance,models,package and
untrusted documentation checks remain unauthorized until one concrete review is
prepared after source verification. Thirty-two dependency wheels and the pinned
6992530-byte Lychee archive remain present with matching hashes;no download or
installation was performed. New package/docs preparers are inert.

### D97 — Bind source, task delivery and installation into one finite review

All13 source checks passed on unchanged4cb0bf74. Both full runs passed1679 tests
with21 skips,total coverage82%,both coverage gates passed;compile,schemas,Ruff,
policy,mypy and wheel/sdist builds passed. Session94490 is terminal. Do not rerun.
The initial78bf fixture failure and later full passing evidence remain separate.

Combined review51c43d2c44eb24c3b4a8d2c355989243fa6f4dec96e924d3e50dc30c370da29c
is prepared with251 verified assets,not approved or executed. It covers fresh
source4cb worker/collector conformance,three offline grader boundary/state probes,
normal grader validation and up to6 development task turns. Same128 existing-grant
operations/10000 reserved seconds/0cash ceiling;explicit component caps sum9600
seconds and117 operations including wrapper margins. No threshold was relaxed.

The independent package componentb88eddf3 binds the new wheel56a86fc3 with32 unchanged
cached dependencies and19 private offline checks. Preparation's no-execution dry
run passed. The docs component62cd8dbb binds the cached6992530-byte Lychee0.24.2
archive and passed six first-party sandbox probes without running the checker.
No downloads,builds/pulls of images,new dependencies,credentials,destinations,
activation,release or old-image/volume cleanup are included. Independent package/
docs execution continues only after model worker/proxy cleanup is verified.

Actual new execution requires approval of this exact combined bundle because
terminald775e93e binds prior source/instructions and forbids retry;the pasted
continuation reserves untrusted execution/installation. Routine definitions and
first-party verification are complete under standing authority. No architecture
decision or further broad source check is needed. Preserve all prior5 actual turns,
29 operations and313.0355685814284 seconds. Grant remains13059operations/3749turns/
118960.73761921376seconds/0cash. Full usefulness,selection,corpus,controls,resource
acceptance and release remain open.

Next:read repository-task-delivery-20261023/README.md and approval-bundle.json;
inspect actual response and markers;record actual parent approval once and execute
run-integration-bundle.py with51c43d2c once if approved. Never run a draft,repeat94490,
or replay terminald775e93e. Continue from actual component results after execution.

### D98 — Accept the repaired journey without upgrading development evidence

The October 24 approved bundle `51c43d2c` completed all three components on source
`4cb0bf74`: six real repairs passed independent upstream grading, all six capture
chains and task-instruction bindings verified, and all three treatment turns
observed optional Ponytail instruction loading. The installed wheel passed 19
checks and cached offline docs verification passed. The canonical audit reconciled
45 completed operations / six turns / 689.980447711423 operation-seconds and
confirmed owned worker removal and the stopped proxy. Provider-internal metering,
semantic contribution and actual provider cash remain unknown. No formal
qualification, usefulness, selection or admission gate closes. See
[the completed development report](../../reports/toolkit-v2/c13/repository-task-delivery-20261023/comparison.md)
and its linked canonical audit. The 35-case pool and remaining 106 cases stay on
the scientific critical path; infrastructure resource acceptance remains separate.

### D99 — Expand the workload pool through the existing optional grader

The next review adds five repositories to curation using the current protected
suite adapter and completed reproduction drivers. The 16 new runtime supports
stay inside one private optional grader image; they are not toolkit dependencies.
MSAL supplies an explicitly authored audit; four other tasks retain upstream
repairs. No core service, new evaluator, live selection claim or threshold change
is needed. The exact review is `be8b0e5f`, with zero models, 13 offline calls,
16 operations and 785 reserved seconds. Static preparation passed; installation
and subject execution remain unapproved. See
[the reviewed scope](../../reports/toolkit-v2/c13/repository-independent-sources-20261024/README.md).

### D100 — Renew expiry without resetting usage, then retain only reproduced cases

Approved `be8b0e5f` ran once on unchanged source `4cb0bf74`. The retained offline
image `b0eb4add` passed three fresh probes; four tasks reproduced and CanvasAPI
remains excluded after an exit-2 collection error, with the exact exception
unknown. Twelve physical receipts/attempts and all 15 operations reconciled;
29.984952959697694 operation-seconds, zero models/cash were added. Owned workers
and canary are absent; both new and parent images remain. The standing finite
budget delegation covered an expiry-only amendment to October28 17:52:35.978639 UTC;
all ceilings and counters were preserved. No permission was inferred from expiry.

[The pool](../../reports/toolkit-v2/c13/repository-independent-sources-20261024/provisional-pool.json) is now39 cases across24 repositories, with102 more needed for
balanced stages. No qualification, usefulness, selection, resource acceptance or
release gate closes. Source/package checks are unchanged and were not repeated.

### D101 — Group cached-suite support without growing the core

[The next review](../../reports/toolkit-v2/c13/repository-supported-suites-20261027/README.md), `c81557a2`, groups six cached suites and22 optional
grader support wheels in one proposed private image from retained `b0eb4add`.
AEEP's existing service, executor, grader, accounting and reproduction drivers
remain the stack. No new core module or project installer is introduced.
All170 required identities/assertions are retained; authored audits and Goodconf's
capture profile are explicit. PyGLS/MCP1864 remain deferred and CanvasAPI excluded.
Preparation passed140 pins,30 grader guards,22 classifier cases,seven budget guards
and pure derivation; no new untrusted execution occurred. At most20 offline calls,
23 operations,1030 reserved seconds and zero models/cash need exact approval.
No architecture decision or repeated source/package/docs execution is required.

### D102 — Retain reproduced cases and diagnose failures before changing dependencies

Approved `c81557a2` completed once. Goodconf, Dishka and Prometheus reproduced;
both MCP snapshots and Twyn remain excluded after collection errors. Exact
exception causes were not retained. All12 physical receipts/attempts and15
operations reconciled, charging35.61532362597063 seconds and zero models/cash.
The unchanged canary and owned containers are absent; retained image `f60342e9`
grew8,527,902 bytes from retained `b0eb4add`. No old image or volume was removed.

[Results](../../reports/toolkit-v2/c13/repository-supported-suites-20261027/RESULTS.md)
and [the pool](../../reports/toolkit-v2/c13/repository-supported-suites-20261027/provisional-pool.json)
retain42 snapshots/27 repositories/2613 required identities. Counts are16 single,
18 multi,8 audit;99 additional cases are needed. Old source/runtime bindings and
all charges remain. Source4cb and completed source/package checks are unchanged.
No qualification, usefulness, selection, resource acceptance or release gate closes.
A bounded diagnostic must establish collection causes before proposing fixes;
terminal execution authority cannot be reused.

### D103 — Diagnose exact failed collections without speculative installs

[The exact review](../../reports/toolkit-v2/c13/repository-collection-diagnostics-20261027/README.md)
`faa10772` is prepared, unapproved and unexecuted. It covers only the four unresolved
collections on their original retained images: MCP222, MCP384, Twyn and CanvasAPI.
The public payloads, tests, bootstrap and plugins are unchanged; a separate
operator collector returns only sanitized exception categories and reviewed public
identifiers. Completed containment evidence is reused. No grade or task eligibility
can be inferred, even if a diagnostic exits successfully.

Static preparation passed37 pins,13 sanitizer guards,three whole-collector synthetic
error/timeout/oversized checks,seven budget guards and actual driver definition/
authority persistence in a removed synthetic database. No subject code ran.
The four-call bound is6 existing-grant operations/290 reserved seconds,zero models
or cash. No build, install, download, new probe, host canary or package/docs rerun
is requested. Product source4cb and the42-case pool are unchanged;99 cases remain.
Actual execution needs one specific approval; routine finite definitions and
expiry amendments remain delegated. No architecture decision is pending.

### D104 — Preserve an inconclusive diagnostic and move to other workloads

Approved `faa10772` completed once; [the result](../../reports/toolkit-v2/c13/repository-collection-diagnostics-20261027/RESULTS.md)
retains the collector's limit. MCP errors were unrecognized, while Twyn and
CanvasAPI reported `ModuleNotFoundError` with names filtered out. Exact causes
remain unknown. No speculative dependency fix or automatic replay follows;
these cases stay excluded while curation moves to other sources.

Four physical receipts/attempts and six operations reconciled, charging
11.11573583446443 seconds,zero models/cash. All owned workers are absent; images
are retained and no host canary was created. Grant13140operations/3755turns/
119727.43407934532seconds/0.0cash. Product source4cb and the42-case pool are unchanged.
No scientific or resource gate closes. New source execution still needs a concrete
exact review; static source/license/workload preparation continues safely.

### D105 — Review actual library tests instead of inferring runtime from metadata

[The next exact review](../../reports/toolkit-v2/c13/repository-library-reproduction-20261027/README.md)
`f0261e6d` is prepared, unapproved and unexecuted: CrossGL257 and Marshmallow-
SQLAlchemy640 authored audits,73 required identities,four reference/regression
payloads. It reuses retainedf603,existing observer and applicable containment;
Marshmallow3.25.1 loads from its already-cached pure wheel. No install/build/download,
new probe,host canary,package/docs rerun or model is needed. Maximum6 existing-grant
operations/290 reserved seconds/zero cash.32 pins,10 grader guards,22 classifier
checks,seven budget guards and synthetic definition/authority persistence passed.

Thirty bounded new source reads produced19 truncated/unparsed archives,10 static-
reviewable sources and one safety exclusion. The index now has163 records; no new
case is counted. Metadata package lists are not a size/runtime guarantee. The named
queue's scope/origin preflight failures are preserved and its final sample excludes
those origins. C++ hooks142 is excluded because required tests can invoke real pip;
no assertion or guard was relaxed to make it fit. The four unresolved diagnostics
remain excluded. Product source4cb,42-case pool and all live counters are unchanged.
No scientific or resource gate closes. Exact new execution is the only pending
intervention; no architecture, infrastructure or budget choice is requested.

### D106 — Complete the library batch and address a verified grader layout limit

Approved `f0261e6d` completed once; both audits reproduced. [The result](../../reports/toolkit-v2/c13/repository-library-reproduction-20261027/RESULTS.md)
retains all73 required identities and rejected regressions. Four canonical receipts/
attempts and six operations reconciled, charging10.159214583225548 seconds,zero
models/cash. Owned containers are absent and all images remain. No install, build,
download, probe, host canary or package/docs run occurred. Grant13146operations/
3755turns/119737.59329392854seconds/0.0cash.

[The pool](../../reports/toolkit-v2/c13/repository-library-reproduction-20261027/provisional-pool.json)
is44 snapshots/29 repositories/2686 identities:16single,18multi,10audit.97 more cases
are needed; old bindings/failures stay intact. Product source4cb is unchanged.
A verified layout constraint blocks ordinary nested test directories: Gabbi342's
published identities begin `gabbi/tests/`, but the current contract only accepts
`tests/`. An explicit versioned extension may reuse current test/source separation
without changing v1-v3 meanings, assertions, identities, thresholds or size bounds.
It is engineering preparation, not authority for new subject execution or a passed
scientific gate. No architecture decision is pending.

### D107 — Support package-local tests through a reviewed v4 contract

[The v4 increment](../../reports/toolkit-v2/c13/repository-test-roots-20261027/README.md)
preserves published package-local test paths through exact operator-owned roots.
Legacy v1–v3 meanings, archive bounds, assertions and acceptance thresholds remain;
the actual retainedd02cb953 recipe rebuilds identically. Same observer, grader,
container and accounting; no new core dependency or service.

All13 source gates passed on86012b45. Both full runs passed1703 tests/21 skips,
coverage82%,both branch gates passed;compile,schemas,Ruff,policy,mypy and builds
passed. Source session42772 is terminal. The44-case pool keeps old source/runtime
bindings; no qualification or conformance transfers. New metadata spans213
candidate rows/97 repositories, not213 reproducible tasks. Eighteen bounded source
reads produced9 inert cases;Sopel is deferred for its runtime/install requirements.

Eight proposed v4 cases retain1033 required identities. Static closure pins12
optional grader wheels/1743060bytes. The source-only JSONPath library is unchanged,
its license commit matches all six files, and its embedded1.3.0 version is recorded
separately from distribution1.4.0. No setup.py runs. The proposed operator observer
can retain bounded public failure tails under exact future approval;four synthetic
checks preserve the stock evaluation. This repairs the diagnostic information gap
without a replay or a default product-retention change. No upstream code, image,
installation or model turn ran. Finish the concrete combined runtime/package/docs
review before requesting its one necessary execution approval.

## D108 — One offline v4 reproduction/package/docs review

Reuse the completed finite container driver and protected pytest grader for the
new test-root contract. Eight public snapshots need twelve optional runtime
wheels and unchanged JSONPath library bytes; the source-only package is copied
with its recovered same-commit license instead of running setup.py. Existing
image configuration and parent layers remain, and all images are retained.

The next exact approval also covers bounded operator-only public failure tails,
the current installed wheel and cached offline docs verification. Earlier
collectors discarded useful collection causes; retaining a bounded tail during
the original call avoids diagnostic replays. The five-field grade and default
product retention do not change. No new framework, core dependency, service,
model authority or architecture choice is introduced. See [the exact review](../../reports/toolkit-v2/c13/repository-test-roots-20261027/README.md).

Static preparation is not reproduction, qualification, comparative usefulness or
selection validation. The44-case pool keeps historical source/runtime bindings;
no stage or threshold is changed to accommodate the new batch. Common uncertainty
stops external dispatch; isolated workload rejection continues only after known
canonical completion and cleanup. Routine finite definitions are delegated, while
new untrusted installation/execution still needs the user's exact approval.

## D109 — Correct effective runtime and test-status framing before more calls

Approved81cce633 reproduced two cases; six remain excluded. Its metadata closure
mixed image-installed and probe-supplied portable wheels. Future preparation must
track those separately and verify the exact task profile. A probe that loads
cached dateutil/six privately cannot establish their image installation.

Retained observations also show application error logs being parsed as test
statuses. Keep the pinned upstream parser body and protected grader unchanged;
first test an explicit operator adapter that frames genuine pytest status rows,
preserving module collection errors, required identities, exits and unexpected
test checks. This is an adapter-fit question, not justification for a new grader
framework or relaxed acceptance. Full original passing output was not retained;
synthetic parser fixtures must be labelled accordingly. See [actual results](../../reports/toolkit-v2/c13/repository-test-roots-20261027/RESULTS.md).

No old failure becomes a pass. A changed optional runtime/observer needs a new
exact review and fresh calls. The unchanged installed wheel already passed19
checks; do not reinstall it merely because corpus preparation continues. Keep
qualification, usefulness, selection and resource acceptance independent.

### D109 correction prepared

[Review27efdd79](../../reports/toolkit-v2/c13/repository-effective-runtime-20261027/README.md)
adds only three cached support wheels to the retained image and tests their
actual image locations with bootstrap-only probe payloads. An explicit operator
adapter frames pytest result rows before the unchanged upstream parser. Seven
synthetic cases preserve collection errors,unexpected IDs and failure behavior;
no real subject result is inferred. Default product behavior stays unchanged.
The review covers six excluded subjects and zero model turns. Source and wheel
checks remain applicable without reinstalling unchanged artifacts. Execution needs
one new exact approval; terminal81cce633 remains intact. No new core dependency,
framework,service or architecture choice is introduced.

### D109 correction completed

Approved27efdd79 reproduced five cases under the explicit image/observer profile.
iCalendar880 remains excluded for16 missing parameterized metadata identities;
899 reported passes do not replace the915-ID contract. Keep that result and move
to independent sources instead of repeatedly repairing metadata through execution.
Image df79d0f3 and all older images remain. All19 operations and16 physical attempts
reconcile with zero models/cash. Source/package bytes and prior checks are unchanged.
See [the result](../../reports/toolkit-v2/c13/repository-effective-runtime-20261027/RESULTS.md).
The51-case pool is provisional;no scientific or resource gate closes.

## D110 — Version larger repository transport before holdout freeze

Two source samples excluded16of20 and19of30 archives at the prototype650KB cap.
That cap is an implementation limit,not a scientific or product requirement.
The operator's resource steering asks for workload-grounded limits. Add an explicit
suite-case v5/mapper profile while retaining v1-v4 limits and serialized recipes.
Reuse AEEP's current container/accounting path and upstream pytest/parser; changing
harnesses would leave the same local byte boundary and add another execution path.
No new core service,installer,framework or database is needed. [The finite plan](../../reports/toolkit-v2/c13/repository-large-archives-20261027/PLAN.md)
records proposed bounds and required checks. They are hypotheses pending actual
source/worker evidence,not production SLOs. Model arguments cannot raise them.
Scientific thresholds,permissions,all old failures and the51-case pool stay intact.

### D110 verification and execution scope

Source1fde passed all13 gates and preserves the actual frozen d02 recipe. Reuse
upstream pytest and the SWE-rebench parser; the optional grader runtime adds only
packages required by the selected test closure. Six larger subjects are proposed.
Smart-open S3 cases are deferred for their separate AWS mocking dependencies.
NetworkX's spectral test requires one pinned SciPy1.15.3 binary, so the next review
explicitly includes its bounded data download, metadata/license verification and
private offline installation. No host/core dependency or service is added.

The review reserves four same-software diagnostic calls and a second setup/analysis
phase for first-party report controls. Repairs require exact recorded digests,
unchanged scientific/protected semantics, known canonical completion and cleanup.
No uncertain retry, new software/task bytes, permission change or product-source
change fits that authority. All usage stays cumulative. The finite bounds are
20 calls/27 operations/1420 reserved seconds, including two fetch attempts and one
build. These limits govern this check; they do not establish product resource SLOs.

## D111 — Pass reviewed framing bounds into the worker entrypoint

The approved2.7MB probe exposed an incomplete D110 change: the outer command
accepted its explicit larger bound,but the worker still rejected input above2MB.
Keep the existing ContainerExecutor and worker. Pass the reviewed bound in argv
only for larger profiles,validate it before the worker reads,and retain legacy
argv/default limits. Do not read that authority from an untrusted JSON payload.
A protocol regression must cross both actual readers; an outer-wrapper mock alone
missed this defect. No new module,framework,dependency,image or service is needed.

The failed probe has complete terminal evidence and absent containers. Preserve
it and all costs; do not call it a pass or replay it. A report collector may
recognize a canonical FAILED attempt as known completion without accepting its
task result. The prior approval's control-repair room excludes product-source
changes,so the new worker/wheel needs an exact executable review after full gates.

### D111 source verification completed

All13 gates passed on374579f1,with1,735 tests in both full runs and82%coverage.
Frozen legacy recipe serialization remains identical. Five collector fixtures
exercise actual code against private copies of terminal evidence,including
incomplete-journal denial. Journal identifiers and canonical repository content
digests stay distinct. The retained image and task bytes are unchanged;fresh
worker/wheel execution requires the exact new review,with no new software build
or architecture. No scientific/resource threshold or prior cost is changed.

### D111 actual execution completed

Approved4661ce49 passes the corrected reader's fresh probes and installed check.
Reuse the source/package evidence;do not repeat broad verification for subsequent
data-only task curation. Isort's missing distribution metadata is a separate
source-project setup exclusion,not another framing failure. Preserve it without
inventing an installed version. All receipts,costs and the earlier failure remain.

## D112 — Count functional multi-file changes,not version bookkeeping

The metadata-selected Pymdown patches each change one functional module and a
version constant in `__meta__.py`. The initial AST body-count heuristic counted
both;that does not establish a multi-file behavior repair. Keep the inert records
and exclude them from the multi-file batch. No model outcome informed this change.
Use published source/reference semantics before freezing task families. No new
core service or classifier framework is needed;record this operator curation
check alongside the existing grader and source pins.

### D112 optional source support and execution scope

Use the existing image/pytest/AEEP path for four genuine multi-file cases. Install
only eight pinned runtime wheels needed by selected tests. Untokenize publishes
only an old source distribution for0.1.1:reuse its unchanged module and exact
publisher metadata/permission notice through the existing reviewed source-copy
pattern. Do not execute setup.py,reimplement tokenization or invent a version.
Fresh probes must bind actual image paths,metadata and module hashes. The new
software/subjects need exact authorization;no source/package regression is repeated
for unchanged core bytes. Keep all initial exclusions and prior costs visible.

## D113 — Let the issue contract determine the required repair

WebAuthn241 asks for SafetyNet basicIntegrity checking. Its full published patch
also removes an unrelated authentication-response field. A smaller repair that
preserves that API satisfies the issue; do not force unrelated cleanup through a
new assertion or count it as a necessary second file. Keep the original failed
multi-file definition. Prepare a new SafetyNet-only task, restore both original
auth assertions and retain all11 required identities. Reference, original and an
integrity-bypass preservation fault must be checked under a new exact review.

Xsdata requires its existing --benchmark-skip config option. Enable the already
installed pytest_benchmark.plugin explicitly; preserve the option, source,
reference, tests and identities. Reuse the four completed source374579f1/image9f47
boundary/state probes and add one exact plugin/config probe. No new dependency,
image, package regression or product source change is needed. Changed protected
payloads require execution approval; routine finite definition work is delegated.

## D114 — Check issue behavior rather than golden patch shape

The completed plugin repair made both Xsdata references pass. Each first partial
also passed, exposing weak issue coverage in the published tests. Keep those task
definitions excluded. For1126, add a distinct-enum lookup check after same-named
nested classes are promoted. For1132, contrast matching and nonmatching decorator
parent paths from the issue. Assert resulting behavior, not exact reference IDs,
source text or a new internal API. Preserve all original assertions and identities,
label authored guards and check reference/original/both partials in a new review.
This is finite pre-campaign grader development, not model qualification or value.
The frozen scientific design and thresholds do not change. No new product module,
image,dependency or package check is justified by these gaps.

## D115 — Distinguish selected installations from cached runtime support

The Markdown pin in a broad support review was not selected for the image's
14-wheel install. A current failing probe established missing distribution metadata.
Current9f47 inherits the historical image;lineage was not the cause. Prefer the
actual selected-install manifest and current source/image-bound observations when
planning a dependency probe. A cached version pin is not installed inventory.
For pending PyMdown tasks,use the existing contained per-payload ZIP-wheel path
with exact pure Markdown3.9 bytes and a fresh import/location/behavior probe.
No new image,installer,core service or source/package regression is justified.
Changed software payloads require an exact review;cached availability grants no
execution authority. Preserve the failed probe and all charges.

After known canonical completion/cleanup,the approved finite first-party report
control allowance can dispatch already-approved unstarted independent payloads.
Record exact control changes and preserve the original cumulative grant anchor;
never use this allowance to change source/tests/reference/software/permissions,
refund an attempt or replay an uncertain call. The XS continuation follows this
rule and is not a new human approval or a successful original markup probe.

## D116 — Use pytest's native identity and result events

The old iCalendar880 reference observed899of915 declared identities. Sixteen
published strings end mid-parameter at whitespace;the protected selector cannot
match them literally. The legacy log parser also splits status rows at spaces.
Keep that case excluded and retain all old costs/results. Do not infer the missing
assertions ran or rename the old observation into a pass.

Reuse [pytest8.3's public hooks](https://docs.pytest.org/en/8.3.x/reference/reference.html#pytest.hookspec.pytest_itemcollected)
for native collection and setup/call/teardown reports in a separate optional
operator adapter. No new core service or mandatory dependency is needed. Keep
legacy SWE-rebench observer bytes and contracts unchanged. Collection returns
identities only,never test success. Preserve stdout as bounded diagnostic data,
not authoritative status rows. Require one-to-one identity provenance,with missing
or ambiguous matches rejected,before any new authored task is frozen. Preserve
all assertions and scientific thresholds. Fresh contained observer conformance,
legacy-equivalence controls and reference/original/partial checks are separate
from model qualification,value,selection and resource acceptance.

## D117 — Version complete pytest identities without reinterpreting old contracts

Legacy SuiteTruth v1–v5 rejects whitespace in required identities. The optional
native adapter alone cannot honestly represent full pytest names under those
contracts. Add case v6 with explicit `identity_format: pytest-native-v1`, inherit
v5 bounds and test roots, and bind a separate hook-based observer. Keep all five
legacy schemas, all three observer/parser files and sampled v1/v3/v4/v5 recipe
digests identical. Preserve every required assertion, missing-result guard,
nonzero-exit guard, frozen threshold and execution boundary. Default replies
retain no logs and reject collection-only requests; only the exact operator
program enables separate collection diagnostics and bounded public failure logs.
No new dependency, runner, image or architecture choice is involved. Fresh source,
installed-wheel and contained observer checks remain necessary. Host fixtures are
engineering evidence; no pool, qualification or usefulness result follows yet.

The adapter choice reuses the existing pinned pytest implementation. The legacy
SWE-rebench log parser splits at whitespace and stays available for old recipes.
Pytest already supplies the native collection and runtime-report interfaces;
small first-party serialization glue avoids adding another reporting plugin and
dependency closure. This is an optional adapter for upstream events, not a new
evaluation engine. No general third-party reporting package is claimed to have
failed qualification;none is needed for this bounded interface.

## D118 — Expand collapsed aliases conservatively during new corpus authoring

Some published log aliases collapse several parameterized tests. Preserve those
old records; do not select one matching test or call that an unambiguous repair.
For a new explicitly authored source scope, freeze an exhaustive expansion rule
before collection: a parameterized alias covers every exact native name whose
first whitespace token equals that alias, plus an exact-name match. Bare function
names require an exact match. Missing groups, overlap between
aliases, conflicting roles, invalid modules and bounds overflow reject the case.
Every added identity becomes required; none is silently removed. This changes no
past result or frozen campaign and is not an official upstream benchmark score.

Freeze and retain the full native crosswalk, F2P/P2P roles, selector archive,
variant payload hashes and expected outcomes after collection and before any body
trial. Collection never proves success. Only the first-party selector literal may
change; preserve upstream source/assertions, patch bytes, permissions and grader
thresholds. A reference must pass every expanded obligation; counterexamples must
show the declared bug while preservation tests remain passing. Cases that fail
these checks stay excluded. No model outcome may influence the expansion.

Reuse the existing optional v6 hooks, AEEP invocation/ledger and reviewed image.
This is a bounded operator data-authoring method, not another core runner or
mandatory dependency. Its exact derivation code and immutable seed assets need
execution review before new untrusted sources run. The existing standing authority
covers finite first-party definitions, not broader software, disclosure or cash.

## D119: Stable contained workspace for path-bearing native identities

JSON-logger's actual reference passed168 tests but could not match three required
traceback parameter names collected in another random directory. Preserve that
failed result and all171 obligations. Do not normalize names, drop assertions,
or accept a smaller denominator. A fixed repository path in each fresh private
container lets collection and body processes generate the same native identity.

Compile an explicit optional operator profile from the existing v6 program. Only
the repository assignment and its mkdir change: `/tmp/aeep-repository-native-v6`,
mode0700, exclusive creation. An existing directory or symlink fails closed;
no caller-supplied path or host mount is added. The container's tmpfs and removal
own the repository lifecycle. Random private logs/wheels remain unchanged. Both
raw and diagnostic output contracts retain their existing meanings. Legacy
programs, packaged core, historical fingerprints and results stay unchanged.

Require fresh containment/native-event checks for both changed profiles, exact
collection followed by a frozen exhaustive crosswalk, and reference/original
checks with all171 obligations. Authored host fixtures alone cannot certify the
container or public task. New execution requires its exact review; unused slots
in the terminalca2a06cc review cannot cover different observer bytes. Dead's
missing Git remains an independent real runtime prerequisite, not a reason to
mock fixtures or change the task. No architecture or scientific threshold changes.

## D120: Real upstream local Git component for repository fixtures

Dead204's actual reference produced33 fixture errors because `git` is absent.
Its protected fixtures require real `git init`, `git add` and `git ls-files`.
Do not mock Git or drop the fixtures. A read-only export of retained image9f47
verified its OCI manifest/config/layers and87 installed Debian packages,without
starting a container. The unchanged230109184-byte owned export was removed.
Git is absent;libc,PCRE2,zlib and the linker tooling are present.

Prepare the exact official Debian arm64 Git2.47.3 archive,8665568bytes,for review.
Select only its unmodified main binary,templates and copyright. This is a narrow
local-command component,not a complete Debian Git package installation. Static
Apple LLVM inspection must confirm the exact predeclared three-library closure;
unknown dependencies stop before build. One local COPY-only image inherits the
unchanged parent configuration and layers. No package scripts,resolver,Perl/Curl
helper stack or host installation runs. Keep both images and the private cache.

The parent review must explicitly authorize the exact download,new component,
image build and deterministic output-image binding. Fresh probes must establish
containment,events,Git version/linking/local behavior and Identify origin before
reproducing all38 obligations. Old reference failures remain. Current source
and wheel checks are reused;no model or scientific/resource/human/release claim.
Isort's actual missing distribution metadata,Sopel's incompatible closure and
SQLglot7479's undetected partial repair remain independent exclusions.

## D121: Promote the verified workspace behavior into the shared v6 observer

The171-test actual check used an explicit operator profile,while the normal CLI
exporter still compiled a random repository path. Keeping that difference would
make future path-bearing workloads depend on a separate custom program. Promote
the same two verified creation lines into the packaged v6 template:one fixed
private path and exclusive mode0700creation inside each fresh contained worker.
No caller path or host mount is added. Existing directories/symlinks fail closed.

The compiled raw program must match the actually checked profile byte-for-byte.
Host tests replace only its fixed literal with exclusively owned scratch and
exercise traceback identity across fresh processes plus directory/symlink
preservation. Legacy v1–v5 schemas and programs remain unchanged. Old v6 recipes
keep their fingerprints and evidence;new source/package/runtime bindings need
fresh checks. Historical171-test source-M1 evidence is not new-source conformance.

The unapproved Git/docs draft765e28e7 is withdrawn before execution because its
source and package assumptions are now stale. Preserve its preparation and the
actual completed ae6a0f9f results. Complete all13source gates,build the corrected
wheel,and prepare one new exact Git/runtime/wheel/docs review. Keep resource
qualification separate from comparative usefulness and live selection;no model,
threshold,permission or architecture change is authorized by this promotion.

## D122: Validate nested execution reviews before combining their bindings

The actual17defe159attempt stopped before external work because its nested
runtime review retained three stale script hashes. The outer preparation copied
the child map,then overwrote those entries with current hashes. That validated
the flattened map while leaving the child's conflicting pins untested.

Keep every terminal review and its original preparation result. Audit each
execution review,template,parent envelope and embedded dependency map before
combining them;reject conflicting pins even when the outer hash is current.
Use one small first-party report helper rather than a new core service. Authored
controls reproduce this exact failure,and the actual driver must stop before
Docker or an execution marker. Preserve unchanged task programs and software.

The already approved unstarted package/docs components may complete after exact
common-source,identity,accounting and no-side-effect reconciliation. They passed
and are not rerun. The failed runtime has a one-attempt boundary;prepare a new
exact runtime-only review instead of silently replaying it. No scope expansion,
budget reset,refund,new model call or scientific gate follows from this repair.

## D123: Reuse the verified Git context and account for its inherited ELF loader

The actual a11807f2attempt downloaded and verified the reviewed Git archive,then
stopped before Docker because the expected dependency set omitted
`ld-linux-aarch64.so.1`. Keep its completed operation and 2.9479576251469553seconds
charged. The archive/context remain unchanged;the exact network-attempt count is
unknown because the local list was lost at the guard failure. The bounded code
allowed at most two attempts. Do not infer a precise count from elapsed time.

A read-only export of the same retained parent verified its OCI configuration,
all layers,the loader path/aliases,and the actual libc,PCRE2 and zlib files. The
unchanged owned export and static ELF scratch were removed;no container started.
The loader is inherited existing software. No library or package is added.

Prepare a new exact cached-context review. Verify all19prepared files,modes,the
archive and actual ELF names before the single COPY-only build. Allow no further
download or extraction. Retain fresh contained Git/linker/local-command probes
and every frozen task obligation. Keep all images and prior evidence. A new
actual approval is required because the terminal review permits one attempt and
forbids automatic retries. Package/docs/source checks remain complete;no model,
architecture,threshold,spending or release decision follows from this repair.

## D124: Keep successful runtime conformance separate from corpus reproduction

The actual cached Git image35dc1bcbpassed both shared-v6 profiles,the real local
Git/linker/Identify checks,Dead's38obligations and two frozen171-test controls.
Its19completed receipt chains,22operations and cleanup reconcile. Add only the
new Dead snapshot to the provisional pool;do not count controls or transfer old
source/runtime case bindings. The pool is65and stages remain unfrozen.

Reuse this exact image/observer conformance for applicable finite source batches
while checking identity and permissions at dispatch. Each new source still needs
its own exact rights,scope,reference/counterexample reproduction and applicable
execution approval. Re-run boundary checks only for a changed or stale binding,
not as a substitute for preparing the missing representative tasks. Preserve all
prior failed charges and keep resource acceptance separate from comparative value.

## D125: Prepare two cached fixed-snapshot audits on the verified backend

Use the independent Param1073 and Jsonpickle587 snapshots as authored audit
candidates. Their source archives and BSD license notices are already cached.
Apply the published source fix to the public snapshot,retain all published
required assertions,and add the explicit byte-preservation guard. The reference
is empty and the original-source counterexample stays private. These are source
contract audits,not complete published repair tasks or official benchmark scores.

Jsonpickle's published patch also changes Git/linter/documentation files. The
reviewed source-only scope keeps the serializer fix and all test-patch bytes,
and records every omitted metadata edit before models or external execution.
No version,distribution metadata,installer or dependency is fabricated. Existing
upstream fallback behavior remains unchanged. The first inert preparation's
asset-adapter and unsupported metadata-scope errors remain recorded.

Reuse actual dual-profile conformance only while sourceb09911a0,image35dc1bcb,
executor definitions,environment and canonical19receipt chains still match.
Do not repeat boundary/default-control probes. New tasks need their own native
collections,exhaustive alias groups frozen before body calls,and reference/
counterexample observations. Require every original alias plus the explicit
preservation guard;predeclare30/83minimum and256maximum expanded identities per
case. No test can be dropped or outcome used to remap the scope. Static fixtures
and reused backend evidence do not qualify either source. New source execution
requires its exact finite review;no model,architecture or budget decision.

## D126: Preserve the actual failed collections and qualify only the missing support

The ca735d78controller used formatted-file digests as canonical JSON wire digests.
Its two bookkeeping operations completed before any source call. A recorded
routine definition/budget amendment corrected only those expected digests under
the standing delegation,retained the two charges,and resumed the same six
unstarted approved calls. Cumulative control allowance was10operations/362seconds;
no source,assertion,payload-file,permission,model or cash authority changed.

The two actual collections then completed and were audited. Param exposed all30
identities but exited3because pytest-asyncio was not registered for its strict
configuration. Jsonpickle exposed81of83required identities:the missing two are
`tests/handler_test.py::ruff` and `tests/object_test.py::ruff`. No body comparison
ran. Both remain excluded. Six cumulative operations/5.994088584091514seconds stay
charged,including the earlier control failure. No case is added to pool65.

Prepare Param only with the exact cached pytest-asyncio1.2.0wheel,15095bytes,
SHA8e17ae5e46d8e7efe51ab6494dd2010f4ca8dae51652aa3c8d55acf50bfb2e99.
Its Apache notice,entry point and Python3.13dependency markers are checked as data.
Keep every original source/test/reference/negative byte and all30identities.
One plugin registration/event-loop fixture plus fresh collection/reference/
counterexample requires new execution approval;the prior unregistered collection
cannot qualify it. No installer,download,image build or new core behavior.

Defer Jsonpickle on this backend. Its original required Ruff items cannot be
removed,and the earlier source-only metadata omission does not qualify that
lint scope. Supporting it would need a separately reviewed upstream Ruff/plugin
and complete applicable configuration path. Choose other independent workloads
instead of expanding the core for one unadopted case. Reused backend conformance,
plugin fixtures and source reproduction remain separate from comparative value.

## D127: Stop corpus expansion and test usefulness on the working pool

The October 29 operator direction identifies an excessive testing loop. Packaging,
dependency, collection and review-hash repairs have displaced the central value
and selection questions. Reconcile actual outcomes and charges, then defer
incompatible optional workloads, including the inert Param plugin preparation.

Use existing AssessmentService, BenchmarkRunner, controlled workers, protected
graders and captures for a bounded development comparison from the 65 working
snapshots. Prepare 21 pairs: seven tasks per family from 21 repositories, with
ordinary capable Codex versus the same environment plus optional Ponytail 4.10.0.
Choose cases before model outcomes, preserve their original assertions and source
notices, isolate public inputs from private tests/answers, and stop on uncertain
execution, accounting, grading, cleanup or capture. Poor candidate performance
is a result, not a reason to replace tasks or expand the corpus.

This intermediate experiment can inform a decision about further investment and
provide task success, resource observations and engagement evidence. It cannot
qualify or admit the candidate or replace the frozen 8/28/105 campaign. The
implementation rejects development-exposed cases even in formal training;
reserve their related repositories outside all later formal stages. Report the
resulting loss of eligible provisional cases explicitly. Keep resource acceptance
separate and do not turn proposed operational thresholds into product requirements.

Follow the result with actual evidence-bound admission/selection restraint.
Positive live selection benefit requires independently established applicable
value and a separate cohort. Do not label every abstention correct merely because
this pilot is inconclusive, or spend new task turns replaying an ineligible
candidate to manufacture a positive selection claim. Each next test must name
the decision it enables and its stop condition. New model disclosure/execution
still needs its concrete scope; no architecture decision is needed.

## D128: Correct the task artifact format without replaying started work

The first approved usefulness attempt used gzip for every task. The existing
legacy decoder requires plain JSON;the mixed recipe's union output schema did
not make gzip valid for every truth version. The prompt fixture missed that
per-case contract. Three turns reached two cases before cancellation. Preserve
their canonical records and charges;exclude both cases from value analysis for
this known engineering defect. Do not call those outcomes capability failures
or retry either case.

All92grader and3task chains reopen as completed,with owned cleanup confirmed.
The report-body reservation was known unstarted:the exact per-trial exception
propagated before report generation or its clock. The existing operation API
settled that unused reservation with explicit operator proof;operations and
three model-turn allowances remain charged. Total105operations/825.743449958507
seconds reconcile. Original terminal files remain unchanged.

The actual parent's routine-control amendment clause and standing definition/
scope delegation cover correct existing artifact profiles for the19unstarted
tasks:13plain,sixgzip. Every original case field and source/test/reference/wheel
byte matches;no product source,grader program,image,model,destination,permission,
metric or intended case slot changes. Both arms receive the same format within
each case. A new strict decoder roundtrip rejects the original mismatch and
checks actual grader payload bounds for all19cases without executing them.

Record exact component definitions and fresh applicable worker evidence. Existing
service grader validation remains mandatory. New reservations enforce BOTH local
component caps and the original13333/3755/120131.70525092818/$0 anchor;synthetic
checks reject parent turn43 in either component. No fresh allowance or human
answer is invented. At most38new turns plus3earlier give41inside42. Known task
failures remain results;common execution/evidence uncertainty stops dispatch.
Keep plain/gzip resource results separate. Nineteen pairs cannot meet the20-pair
resource-interval minimum or qualify/admit. Report two censored slots and all
attrition explicitly;do not replace tasks to recover a favorable result.

## D129: Preserve the observed tie and enforce task codecs before model work

The corrected19-pair development comparison completed on sourceb09911a0. Both
arms passed14/19 with identical task outcomes. All38token capture chains verify
and all19candidate instruction loads are positive;semantic contribution and
provider-internal metering remain unproven. Plain and gzip resource conditions
stay separate,with only11and3both-successful pairs. No supported savings or
broad usefulness verdict follows. The actual admission API rejected both real
development reports without changing admissions/counters. Positive live selector
benefit remains a different unproven result.

Retain two engineering-censored slots and their3turns. All323operations/41turns/
5137.359838171862accounting seconds/$0 reconcile,within the original approval.
All21source repositories were exposed;24related snapshots leave all formal stages,
leaving41potential snapshots. No stage/count/threshold is relaxed. Do not spend
more turns merely to recover a20-pair count or hunt a favorable candidate result.

The known controller mistake should become an early product validation error.
After the completed study/audit/admission check,add a narrow provider-neutral
check for standard repository artifact fields versus scheduled task codecs,
before budget preview or model execution. It must reject mismatches without
changing legacy decoder/receipt meanings or inventing output conversions. Keep
custom/direct outputs under their existing review/grader requirements. Run the
required software checks for this actual code change;historical live evidence
stays bound to b09911a0. No additional model turn is needed for the guard.

## D130: Reject mismatched standard patch bridges and prioritize task value

On October 29 the operator objected to the helped CLI-control exercise as a user
gate and reiterated the central question: does a capability materially help a
task? Remove that exercise from the critical path. Retain the objection and prior
responses without claiming human-control qualification or altering old evidence.

The actual 19-pair study observed zero additional successes with optional Ponytail
4.10.0. The protected-test diagnosis finds remaining bug checks in four failed
repair cases and preservation failures in the fifth. Both canonical arms fail
those same five cases. Supplemental observer details lack a direct arm reference,
so they remain unordered within each pair. Preserve that limit. Keep the baseline
for this tested scope; positive live selection benefit remains unproven.

The small provider-neutral source guard now rejects incompatible standard managed
artifact fields during budget preview and dispatch verification. It accepts both
corrected definitions and refuses the actual failed mixed plan before reservation,
with counters unchanged. Direct/custom artifacts retain their existing contract.
No decoder, schema, third-party dependency, worker image or model changed.

Source 5a4257e3 passed all 13 gates: 1786 tests/21 skips in each full run, 82%
coverage, both branch gates, schemas, ruff, policy, mypy across 168 files and build.
Historical live results retain source b09911a0. Current installation needs three
focused checks of the changed artifact. Prepare one exact bundle with the 32
cached dependencies and pinned offline docs checker before asking for the
installation/execution authority excluded by the comparison review. No new model
or architecture decision is needed. C13 remains IN_PROGRESS.

## D131: Complete current-artifact checks and keep the beta decision scoped

The operator approved exact bundle 88e5c1b9. It completed once: all three installed
checks passed, followed by offline docs verification on 69 bound inputs. Both
private runtimes were removed unchanged. The audit matches all 168 Python wheel
members to current source 5a4257e3 and preserves the 33 cached wheel archives.
No models, downloads, Docker operations, cash or grant changes occurred.

The engineering recommendation is LIMITED_BETA for private experiments on the
tested macOS arm64/Python 3.13 setup. Production release and public benefit claims
remain NO_GO; operator publication approval is absent. C13 remains IN_PROGRESS
for unmet acceptance. The completed source b09911a0 comparison still has identical
14/19 outcomes and no demonstrated incremental benefit. Positive live selection
benefit and formal qualification remain unproven. Another efficacy study needs a
justified hypothesis, untouched cases and applicable exact authority. Preserve
these limits instead of replaying models or expanding infrastructure tests to
fill checkpoint counts.

The 69-input docs result binds its actual files before routine status updates.
Keep those hashes and results unchanged. No further checker approval is needed
solely for this progress record. The operator's clarification keeps the helped
control exercise off the critical path.

## D132: Reconcile public evidence before another capability study

The October 30 continuation found the native task idle at `c70c9c5`. Its completed
19-pair optional-skill comparison supersedes the active guide's October 7 status
as the latest evidence entry point. Update the guide and index while preserving
all historical records and source scopes. Reuse the existing `aeep_value` contract
for a future three-way study; do not add an engine or force a candidate to win.

No new hypothesis is established by the negative Ponytail result. Prepare a
specific capability/workload rationale and current independent qualification
before freezing fresh cases or requesting execution. The 41 potential snapshots
are not an adopted cohort. Corpus work stays deferred. No release, installation,
model or checker authority transfers from a terminal review to changed inputs.
The continuation audit records factual cross-checks and remaining bindings.

## D133: Prepare missing study inputs; reuse the installed Markdown checker

The next-study packet is NOT_READY_FOR_EXECUTION_REVIEW. Do not choose another
candidate solely because the Ponytail result was negative or a newer package
exists. First document the workflow, independent success contract, baseline
limitation and candidate mechanism. Preserve all exposure exclusions and existing
qualification/value contracts. Exact next-run bindings and budgets remain unknown;
a historical route fingerprint is not current-source conformance or authority.

The pinned Markdown checker is already cached. Its declared CLI completed a
read-only, network-denied 69-input scan with zero issues. No install or npx ran.
A zero-exit library import was a launcher no-op and is explicitly not validation.
Lychee is absent; preserve that tooling gap separately from actual link errors.

## D134: Deliver an assembled workflow with three independent acceptance gates

The operator prioritizes reusable stack integration over more Ponytail campaign
work. Audit actual source/interfaces and retained executions before selecting
components. Keep the managed D40 fallback, existing benchmark tasks, isolation,
telemetry and canonical reporting. A named hash-bound workflow delegates to that
existing CLI; it adds no engine, service or database. Source `24dccd3e` passed 13
software checks, including 1,798 passed/21 skipped per full run and both coverage gates.

Working stack integration, candidate usefulness and AEEP selection usefulness are
independent gates. Synthetic interfaces, component availability and admission
restraint cannot substitute for real comparisons. Preserve all negative Ponytail
results and exposure exclusions. Do not replay them for counts. Preserve Ruff
where already ordinary; a duplicate wrapper is a negative/skill-only contrast,
not a reason to remove the existing tool. LibCST is a distinct proposed migration
mechanism, with usefulness unproven. Generic specialist worker profiles and
individual/bundle telemetry remain engineering work, not architecture questions.

Actual approval `732f9cdd` ended at Docker125 before installation. Its private
configuration hid installed Buildx, and the driver also compared raw versus
sanitized failed receipts incorrectly. Retain the failed receipt, complete
journal, terminal attempt and two operations/2.255710876081139sec. No image or
specialist check ran. Help-only observations validate the corrected credential-free
plugin discovery and canonical receipt guard. Because the exact review forbids
automatic retries, one fresh bounded amendment needs approval. It changes no
external software, probe, source, model, destination or cash scope. The existing
grant's expiry-only extension preserves counters and absolute ceilings.

The current [delivery packet](../../reports/toolkit-v2/c13/stack-delivery-20261030/README.md)
records source checks, audit, wrappers, failure reconciliation, corrected review
and subsequent work. No candidate activation, public release or benefit claim.

## D135: Complete all recommended integrations before new comparisons

The operator explicitly selected every upstream integration as the next delivery
gate, and equal priority for document/data and software-engineering SkillsBench
tasks. [STACK_COMPLETION.md](STACK_COMPLETION.md) records the accepted plan.
Components remain individually selectable. Installation, availability, functional
integration, candidate usefulness and AEEP selection usefulness remain distinct.
Source-only catalogs, report imports and mock fixtures do not pass integration.

Park the pending specialist runtime review and all new comparative campaigns.
Preserve prior Ponytail results, source pins, exposure exclusions and costs. Build
thin adapters around existing software and connect the existing CLI, setup,
workers, grading, telemetry and canonical reports. Retain reusable reviewed
runtimes; never add a second scheduler, event store or graph engine. Langfuse is
selected, Phoenix remains an alternative, Archestra remains research, and the
OpenSkillEval dataset rights exclusion stands. Existing authority and release
restrictions remain. This is product ordering, not approval to install or execute
new untrusted artifacts, start services, use credentials or spend cash.

## D136: Separate finite stack checks from formal case materialization

Use explicit setup v2, `assessment.integration-cases.v1` and plan v7 for one to six
distinct upstream integration tasks. The existing setup service, record store,
workers, execution controls and reports remain responsible for the resulting
plan. Integration requires reviewed pack, recipe, environment, task set and
required-use experiment definitions. It schedules one candidate route and cannot
qualify, admit or establish candidate/selection value. Formal v1 case sets still
require 141 cases; no six-task template expansion or threshold change is allowed.

Workflow preparation is an explicit operator step after an exact inert preview.
It creates no grant, definition review, installation or job. Resolve asset-use
determinations from current canonical reviews, bind original public task bytes,
and keep verifier/oracle bytes outside the worker payload. Retain a preparation
intent and result in the existing store. An interrupted intent cannot silently
create another plan; a completed draft can be exported again without reproposal.
These are implementation rules under the standing finite test-definition
delegation, not new untrusted execution, disclosure or installation authority.

## D137: Let upstream scheduling call the canonical trial runner

Add a scheduling port to BenchmarkRunner rather than another execution or
accounting implementation. Setup v3 and plan v8 freeze an exact external
scheduler definition for the bounded integration case set. Historical setup
and plan versions retain their serialization and managed behavior. A missing
or different scheduler must stop before claiming a job; no fallback is inferred.

The ASE child subclasses the actual AgentHarness and uses the actual EvalRunner
and deterministic assertion API. Opaque slots map to the existing canonical
trial execution, preserving its order, durable claims, worker boundaries,
reservations and protected grading. Upstream assertion results check canonical
grade certificates, not an independent second task oracle. Reject missing,
repeated or reordered slots and mismatched grades. Native upstream Codex launch
and parsing remain unsupported; D40's selected managed fallback remains available.

Bind all 16 upstream Python files, the exact entrypoint, sandbox profile and
complete retained runtime tree. SDK overhead excludes awaited canonical trial
intervals; raw upstream compatibility token/time defaults are never measurements.
No new scheduler service, database, provider or graph engine is introduced.
Source fixtures do not establish actual upstream execution. New software and
models still require applicable exact authority, and the complete-stack barrier
continues to block comparative campaigns.

## D138 — Account for the operator wrapper without another cost store

Use the existing assessment grants, operation ledger and receipts for workflow
inspection, preparation and export overhead. An optional, exact reviewed scope
binds source, files, selection and existing authority. No grant or permission is
created by its storage or selection. Keep unmetered commands compatible and
label their missing overhead coverage.

Exclude the awaited canonical assessment interval from wrapper wall/process CPU;
retain raw spans and all inner charges. Do not turn required legacy vector zeros
into measured tokens, memory or cash. Measurement ends before its own persistence
and Router close. Canonical plan links prevent charging an unrelated grant or
definition. Check unresolved operations and reserve atomically so concurrent
wrappers cannot bypass recovery. No retries or counter resets are added.

This source increment does not complete component setup/readiness accounting,
real SDK execution or either domain journey. The all-integration barrier remains.

## D139 — Selected runtime lifecycle reuses the installer and ledger (November 2)

Connect explicit named runtime bindings to ordinary workflow setup/readiness/
removal commands. Require exact operation-specific review and accounting v2 for
writes, retain independent failure journals and recheck authority/source before
each destination. Preserve unchanged v1/v2 serialization when bindings are absent.
Preserve known unselected consumers, including the parent of a canonical export.
Do not add a runtime manager, scheduler or registry. Installation is not evidence
of enablement, permission, functionality or usefulness.

Approved SDK5136b81a passed installation, containment, real Graph composition
and installed-source checks; Framework hit the immutable-record guard. Its66848247
continuation then failed the first-party driver's missing required description.
Keep both attempts terminal and their costs/evidence intact. The new Framework
review validates complete executor/context/receipt construction and an actual
standard-library denial probe before requesting approval. No successful SDK or
package check is repeated. All comparative campaigns remain paused.

The actual482c8c11 attempt then exposed Framework1.21.0's mandatory context type.
Bind the concrete lazy-loaded `WorkflowContext[dict, dict]` on callbacks and make
the development substitute reject the old `Any` signature. Preserve the failed
receipt. Group current-wheel installation and the corrected Framework check under
034f218d, gated on complete current-source verification. Keep dependency pins,
previous runtimes and Graph evidence; no comparative campaign resumes.

Approved034f218d now passes on current code: installation/idempotence, both
boundaries, all five real Framework checks and installed workflow CLI/schema/
source verification. Its five owned operations are settled; zero models. The
runtime and all old runtimes are retained. All13 source gates pass on e363cfa5,
with1977 passed/21 skipped per full run,83% coverage and both branch floors.
This is bounded component evidence, not an ordinary two-domain journey or a
full-stack, candidate-value, selection-value, resource or release pass.

## November 2: optional scanner in the ordinary workflow

Bind selected static scanning to the existing container executor, canonical
journals, operation ledger and report path. Use a separate explicit scanner
request and accounting v3 for wrapper costs; older scopes cannot authorize the
new stage. Require current source/candidate/runtime and settled receipt bindings
before attaching observations. Retain the reviewed image and private runtimes.
Keep snippets, task content and diagnostic text out of persisted findings.
Candidate staging excludes evaluation answers before canonical inspection.

The approved selected scan 84365d39 passed on the prior e363cfa5 source. A
bookkeeping-only amendment preserved old control evidence by choosing new output
paths before that call. Five total operations remain settled. The ordinary CLI
launch has changed worker/user/mount bindings and therefore needs its own exact
execution review. These engineering checks supply no task, usefulness, resource
or release result. No comparative campaign resumes while the stack gate is open.

## November 2: separate protocol and scanner interpreters

Use the existing parent-image Python for AEEP's containment protocol. Use Cisco's
private environment only for its scanner child. The actual boundary failed before
scanner import. The inspected private environment cannot supply AEEP's required
dependencies; the original stderr was not retained for full failure attribution. No new package or image is needed for this correction.
The source regression binds both interpreter choices. Current full verification
is blocked by real host headroom,not marked passed. Preserve the successful docs,
failed charge,all backups and Docker resources. Resume from the
[carrier handoff](../../reports/toolkit-v2/c13/workflow-scanner-carrier-20261102/README.md).

## November 3: prepare a temporary storage exception

The operator selected preparation of a temporary lower-reserve exception after
usable capacity stayed below 50 GiB. The proposed bundle uses a 42 GiB floor,
1 GiB net host-capacity stop threshold and maximum 24-hour window. Execution
needs exact approval. The default 50 GiB policy and v1 review digests stay.

V2 installation/preview contracts bind one destination, filesystem device and
wheel set. Recheck real space and expiry, retaining failed effects and readings.
Synthetic unit-test capacity cannot replace host measurements. Preserve original
grant counters, backups and existing Docker resources. The
[grouped correction](../../reports/toolkit-v2/c13/scanner-storage-review-20261103/README.md)
locks scanner/package execution behind all 13 source gates. Benchmark, utility,
model authority and release requirements are unchanged.

## November 3: use actual free space for the shared-host source guard

The completed regression run passed 2,021 tests / 21 skips. The subsequent coverage
run was interrupted by a 1.25 GiB net-host-space limit while 61.88 GiB remained free.
A net change on a shared host cannot identify this task's allocations. Preserve
those observations and partial coverage; propose one coverage-only completion
using the normal 50 GiB actual free-space floor. Keep net changes as diagnostics.
Reuse exact-source successful checks rather than replaying the full regression
suite. The original installation plan and its own controls remain unchanged.
See the [bounded completion](../../reports/toolkit-v2/c13/coverage-completion-20261103/README.md).
Exact approval remains required because the preceding review allowed one attempt.
Comparisons stay paused and no integration or usefulness gate closes here.

## November 3: retain the verified scanner/runtime and reuse completed checks

The actual ordinary CLI scan now passes on `c2eb4a3d`, together with all 13 source
gates and the original retained-wheel check. Keep its canonical scan record,
receipt, journal and settled costs. Report the INFO missing-license finding and
unknown safety. Reuse this evidence within its exact source/runtime/candidate
scope; no repeat is justified merely to add test counts. The generic all-stack
probe contract still needs truthful bindings from each component's actual record.
Do not manufacture probe events or broaden this scan into a task/utility result.
Continue the real evaluator and protected task-pack paths; comparisons stay paused.

## November 3: verify real ASE SDK behavior before controlled model execution

Use the retained pinned scheduler/grader and production AgentHarness bridge on
explicit certificate fixtures before preparing a model-backed journey. This
check selects no FakeHarness and makes no task, worker or usefulness claim.
Keep parent-owned responses and candidate bytes read-only to the SDK; use the
restricted, fingerprint-bound local Git helper. Record actual SDK costs in the
existing shared ledger, preserving ceilings, counters and unresolved old work.
The [prepared review](../../reports/toolkit-v2/c13/ase-runtime-contract-20261103/README.md)
needs applicable upstream execution authority. The successful current-source,
scanner, wheel and original-input docs checks are reused within their scopes.

## November 3: retain actual ASE contract evidence without claiming worker execution

Approved `85ba0df6` passed the real scheduler/grader bridge and offline docs.
Record the two synthetic certificate fixtures as SDK conformance only. A future
controlled-model task needs its own reviewed worker, proxy, task, grader and
finite authority. Preserve existing costs, the two older unresolved reservations,
all runtimes and successful exact-source checks. Keep comparisons paused. See
[actual results](../../reports/toolkit-v2/c13/ase-runtime-contract-20261103/RESULTS.md).

## November 3: test controlled evaluator execution through the ordinary CLI

After the actual ASE contract passed, prepare one real task per explicitly
selected engine. Use a neutral source-bound skill and the established public
repository grader; no Ponytail or usefulness campaign resumes. Preserve the
original task's plain JSON output contract in both workers. Keep the full
SkillsBench domain journeys as separate unfinished milestones. The
[exact grouped review](../../reports/toolkit-v2/c13/ase-controlled-workflow-20261103/README.md)
requires two model reservations maximum and actual fresh containment/capture.
Existing successful checks and old charges are retained, not replayed for counts.

## November 3: make canonical worker readiness an ordinary preparation step

Paired inspection and canonical conformance are separate records. The ordinary
CLI now prepares the latter from actual settled observations, retaining the
existing operator review before use. No reported pass flag or metadata preview
can supply missing probes, identity, cleanup, source or charge evidence. Preserve
historical semantics and keep this command outside model-facing tools. The
[implementation and verification](../../reports/toolkit-v2/c13/worker-readiness-correction-20261103/README.md)
remain separate from actual worker/model execution. Correct image directory modes
under a new bounded review; do not replay the failed parent attempt.

## November 3 — canonical readiness and corrected engineering fixture

The ordinary readiness command is verified on current source through all thirteen
source gates. Actual controlled ASE/managed dispatch is still unproven. The
stopped review retains its costs and image; no model ran. The prepared correction
uses the existing symlink strategy and a nonrecursive neutral fixture, preserving
the skill guard. See the [bounded correction](../../reports/toolkit-v2/c13/worker-readiness-correction-20261103/README.md).
The [six-task transport audit](../../reports/toolkit-v2/c13/skillsbench-transport-20261103/README.md)
is static preparation only: original tasks fit, restricted skills are excluded,
and asset rights/runtime/reference gates remain open. No comparison resumes.

## November 3 — actual worker readiness and scoped integration preparation

Review `9d7a7ec5` passed the corrected image, actual paired worker/collector
checks, ordinary readiness CLI and reviewed consumption on source `c48e931b`.
The wheel and offline docs passed independently. The engine stopped before
grading, SDK dispatch or any model turn because scoped preparation omitted
integration case sets. Preserve the [actual results](../../reports/toolkit-v2/c13/worker-readiness-correction-20261103/RESULTS.md).
The narrow resolver correction accepts only the exact bound v7/v8 task set and
excludes unrelated tasks; it does not create a legacy alias. Focused and actual
stored-plan constructor checks pass. Full source verification is running. No
evaluator, SkillsBench, usefulness, resource or release gate is closed by this.

## November 3 — verified integration snapshot correction

All thirteen source gates pass on `cfc36a2a`, with2,052tests/21skips in each
full run,82.63%combined coverage and both branch gates. The corrected stored-plan
constructor passes without upstream execution. The [fresh review](../../reports/toolkit-v2/c13/integration-snapshot-correction-20261103/README.md)
reuses image`bf4581894c1d`; it proposes no new build or dependencies. Fourteen
operations remain charged inside the original cumulative envelope. Engine turns
are still unstarted and need applicable current-artifact execution authority.
SkillRank's [pinned source audit](../../reports/toolkit-v2/c13/skillrank-interface-preparation-20261103/README.md)
identifies its actual core callback interfaces and loopback server, with registry
licensing separate. It is preparation only;86 locked packages are not cached and
no SkillRank code ran. All stack/usefulness/resource/release gates stay separate.

## November 3 — retain real evaluator execution and report-only repairs

[The completed engineering bundle](../../reports/toolkit-v2/c13/integration-snapshot-correction-20261103/RESULTS.md)
establishes actual ASE scheduler/grader dispatch into controlled workers and a
separately selected managed-engine journey. Both protected binary grades passed.
Keep the one-task scope, provider-report token trust, unknown semantic invocation,
all controller failures and original counters explicit. The original two-turn
allowance is exhausted. Do not rerun the tasks to repair serialization.

Encode non-identifier family labels one-to-one at the report boundary and retain
their original labels, without changing canonical tasks or weakening the existing
wire schema. The current ASE report uses an explicitly adapted read-only export;
ordinary adapter support is the next engineering correction. The managed ordinary
CLI export already passed after pretrial metadata encoding. This is stack evidence,
not candidate benefit, selection benefit or either SkillsBench domain journey.
All-stack remains open and comparisons remain paused. Waza still lacks supported
backend access; independent safe integration work continues.

## November 3 — preserve source pins and fix ordinary family-label export

The [ordinary report correction](../../reports/toolkit-v2/c13/report-family-serialization-20261103/README.md)
encodes non-identifier family labels without changing canonical tasks, merging
families or changing the v1 wire contract. All thirteen source gates pass; prior
actual evaluator evidence keeps its original source and explicit adaptation scope.
No model is replayed for formatting. The new wheel and current docs need their
own applicable execution review.

Keep SkillRank pin`5216bae9149b4ff8a7f9e014b6889fb094cee8e1`. Its published0.1.5
binary is built from another commit with six compiled-file differences. The
[grouped preparation](../../reports/toolkit-v2/c13/skillrank-build-preparation-20261103/README.md)
therefore proposes an offline source build using existing Docker controls, followed
by actual upstream local search/show and stop checks. No substitute registry,
compiler installation on the host, native unqualified agent launch or model call
is proposed. The runtime and compiler image remain reusable. Bounded evaluation
callbacks and ordinary workflow composition still need implementation/verification;
search/show cannot close that gate. All comparisons remain paused.

## November 3 — retain installed report verification and audit the entire Cargo license closure

The [actual grouped results](../../reports/toolkit-v2/c13/skillrank-build-preparation-20261103/RESULTS.md)
passed the corrected wheel and72-input offline docs check. Preserve those completed
checks. SkillRank stopped at the first-party SPDX allowlist before the image pull
or any upstream executable. The verified Adler source offers0BSD,MIT or Apache;
its token rejection is our guard defect,not a failed upstream build.

The [remaining-only review](../../reports/toolkit-v2/c13/skillrank-license-correction-20261103/README.md)
compares every actual manifest against the86-version checksum-bound license
inventory. It preserves source/dependency/compiler pins,old charges and the
original40-operation/4,500-second/zero-model grant. Extend only expiry if needed;
never reset counters or replay package/docs. Retain the checked coordinator
snapshot so independent implementation can continue. No source or architecture
selection changes,redistribution clearance or capability benefit is inferred.
Comparisons remain paused;all-stack and bounded SkillRank evaluation remain open.

## November 3 — retain the built SkillRank runtime and connect ordinary lifecycle

The [approved source build and upstream registry checks](../../reports/toolkit-v2/c13/skillrank-license-correction-20261103/RESULTS.md)
passed with the original grant/counters and source pin. Retain the binary,image,
verified dependency cache and receipts. Search/show is executable component
evidence; bounded evaluation and ordinary workflow integration remain open.

Extend the existing owned installer with hash-bound file artifacts for reviewed
upstream binaries, retaining its journal,space guard,exact preview,idempotency
and conflict-preserving removal. This fills its observed Python-wheel-only gap
without another installer service or registry. Keep wheel v1/v2 behavior and
source/permissions/accounting boundaries. No installation toggle becomes execution
permission,qualification or usefulness. Comparative campaigns remain paused.

## November 3 — select the retained catalog through the ordinary CLI

The [file-runtime/catalog increment](../../reports/toolkit-v2/c13/workflow-skillrank-20261103/README.md)
extends the existing installer and contained executor. It adds no registry,
scheduler, database or host activation. The selected binary is the one already
built from SkillRank pin `5216bae9149b4ff8a7f9e014b6889fb094cee8e1`; no pin changes.
Installation, functional catalog execution and bounded evaluation stay distinct.

Current-source CLI execution is pending its concrete grouped review. First-party
wiring checks and the synthetic driver journey are not upstream proof. The
review reuses the original grant and its remaining operations, preserving all
old charges. Real catalog queries stay offline; query/result contents are
transient and canonical records retain digests and receipt/journal references.
Comparisons remain paused and no complete-stack gate is promoted.

## November 4 — retain completed installation/docs and isolate the failed probe

The [actual grouped results](../../reports/toolkit-v2/c13/workflow-skillrank-20261103/RESULTS.md)
passed setup/idempotency, both ownership inspections, installed wheel and offline
docs. The containment call failed before catalog execution. Its discarded inner
error cannot be reconstructed from the retained assertion; the cause remains
unknown. Accepting only `PermissionError` also misses read-only-filesystem denial.

The [remaining runtime review](../../reports/toolkit-v2/c13/skillrank-cli-continuation-20261104/README.md)
adds explicit diagnostic categories and a pinned-binary version check. Preserve
all 24 old operations and passed components. Only first-party probe/driver code
changes; product source and its all-13-gate proof remain unchanged. The finite
two-operation amendment is delegated and prepared, not applied. New contained
execution still requires exact authority. No rerun of source, wheel or docs.

Independent MCP work must represent real database-table outputs, not invent a
file output for the selected state-changing upstream tasks. Preserve the two
packs' different prompts, protected verifiers and grading semantics. No database
service or task is executed by this preparation. All stack/usefulness/release
gates stay separate and comparisons remain paused.

## November 4 — represent database outputs without changing file-pack v1

The [MCP state-pack increment](../../reports/toolkit-v2/c13/mcp-state-packs-20261104/README.md)
adds a separate versioned contract for original PostgreSQL table outputs. Ordinary
inspection verifies the selected assets; the existing file transport and canonical
file preparation reject these tasks until a reviewed MCP runtime and protected
database verifier are connected. Preserve MCPMark's separate oracle and MCP-Universe's
embedded answers, different prompts and original assertions. Their related tasks
cannot increase independent usefulness counts.

All 13 source gates pass on the exact recorded working tree: 2,115 tests/21 skips
in each full run, 82.65568708183221% combined coverage and both branch gates. A
retained source snapshot and inventory preserve separate uncommitted CI inputs;
the feature commit does not take those edits. The new wheel is built only. The
new guide is outside the earlier completed documentation check. First-party
contract tests establish no MCP reference journey or component qualification.

ToolHive retains its selected source pin and can start from the fingerprinted
installed Go compiler; no compiler or dependency was executed. Complete source,
module/license and service permission closure remains open. SkillRank continuation
review1a091b2b stays frozen and pending, independently of these source changes.
All resources, historical charges and comparisons-paused policy are preserved.

## November 4 — retain the completed SkillRank CLI journey

The [approved runtime continuation](../../reports/toolkit-v2/c13/skillrank-cli-continuation-20261104/RESULTS.md)
passed actual upstream version/search/show and missing-record handling through the
ordinary CLI. Authored local catalog entries establish query integration only.
Shared installation and conflict preservation passed; the new disposable copy
and four owned containers were removed. All old resources and charges remain.
The grant now has42operations,zero models and63.68363312864676measured seconds;
the delegated40→42amendment changed no time/model/cash ceiling. Accounting and
cleanup are settled. Passed package/docs components were not replayed.

Root writes were denied withEROFS30 and external networking had no route(errno101).
Retain that distinction; the earlier discarded inner failure stays unknown.
SkillRank bounded evaluation remains open. Continue independent Langfuse and
ToolHive/MCP work; no comparative campaign or full-stack readiness is inferred.

## November 4 — connect minimized receipt export and bind a published Langfuse runtime

The [ordinary CLI increment](../../reports/toolkit-v2/c13/workflow-telemetry-20261104/README.md)
uses the existing HTTP executor, receipt store and assessment ledger. It adds no
background exporter, scheduler or database implementation. Exact definitions and
receipt hashes, disabled configuration, revoked/source-drift guards and durable
one-attempt identities control export. HTTP now performs its final invocation
check before creating the request client. Raw transport dimensions and exclusive
wrapper measurements remain; accepted HTTP does not prove ingestion or linkage.

All13 source gates pass on5a13a630:2134tests/21skips twice,82.697017447269%combined
coverage,both branch gates and packaging. First-party HTTP/driver substitutes do
not qualify Langfuse. New wheel5fe1fa9ba780 and changed offline docs remain unstarted
pending the concrete grouped review. The tested mixed working tree is preserved
in a408-file private snapshot; unrelated operator CI changes stay out of this commit.

Resolve the observed source/artifact mismatch by selecting the actual published
Langfuse4.55.0 commit5e4db922e9021083500cd066249b220a414b7dfe. Originalc106bb3d has
no matching SHA image in either queried registry. Both releases have the identical
OTLP API Git blob3ff63598128b16a2b701c72788a636fbc305a598. Preserve the old pin's
evidence and assert interface compatibility only. All6 ARM64 image/config pins
are verified as metadata. No layer was downloaded or guest program executed.

The grouped review proposes bounded image acquisition/static inspection and
independent current-wheel/offline-doc checks, retaining all resources. Source
license and startup inspection precede a separate service/owned-credential review.
A new31-operation/zero-model/4200-second/$0 engineering grant is prepared in the
existing database, preserving every old grant/counter. The50GiB reserve remains;
no host/Docker memory change is inferred from upstream production sizing advice.
Full-stack, usefulness, resource and release gates remain separate; comparisons
stay paused. Waza still lacks supported backend access.

<!-- workflow-telemetry-artifacts-pass-20261104:start -->
## November 4: acquired artifacts verified; Langfuse service remains unstarted

[Actual artifact results](../../reports/toolkit-v2/c13/workflow-telemetry-20261104/RESULTS.md) pass six image pulls, twelve static audits and
thirteen installed CLI checks under approved d7f05c3f. No service, guest program
or model ran. Reuse the retained runtime and images. Artifact accounting is
26/0/77.50283324997872seconds; old SkillRank counters remain42/0/63.68363312864676.
Both grants are settled. Docs attempt1 failed six duplicate blank lines; the
correction awaits the next service/docs review. Original input evidence remains.
Stack, candidate and selection gates stay open and comparisons remain paused.
<!-- workflow-telemetry-artifacts-pass-20261104:end -->

<!-- langfuse-service-review-20261104:start -->
## November 4: actual receipt ingestion is the next component gate

[The concrete service/docs review](../../reports/toolkit-v2/c13/langfuse-service-20261104/README.md) reuses the current installed CLI and
six acquired images. One local receipt export, exact trace/span/hash readback and
disablement must pass before claiming Langfuse ingestion readiness. The proposed
63-operation/zero-model/3200-second grant changes no existing counter. The4GiB
service cap is an engineering proposal, not product resource acceptance.
First-party driver and standard-library sandbox controls pass; actual startup
remains unapproved/unstarted. General v1 HTTPS-only setup cannot represent this
local HTTP permission and remains a visible workflow limitation. Both SkillsBench
domains and remaining integrations stay open. Waza lacks supported access.
Comparisons remain paused; stack, candidate and selection gates stay separate.
<!-- langfuse-service-review-20261104:end -->

<!-- pipeline-authority-and-langfuse-result-20261104:start -->
## November 4: new pipelines delegated; repeated attempts require approval

The operator approves new finite pipeline work and requires approval for repeats.
Existing paid/credential/release/comparison/storage boundaries remain.
[The approved service/docs result](../../reports/toolkit-v2/c13/langfuse-service-20261104/RESULTS.md) passes the72-input offline docs
check. The service stopped before startup on a manifest/config-ID assumption;
its6operations/0models/0.5966351674869657seconds remain charged and settled.
The corrected service and repaired first-party fixture repeats are prepared,
not run. No passed wheel/source/docs check is repeated. New independent ToolHive
preparation remains eligible. All-stack and both domain journeys remain open.
Comparisons stay paused; candidate and selection usefulness remain separate.
<!-- pipeline-authority-and-langfuse-result-20261104:end -->

<!-- toolhive-first-pipelines-20261104:start -->
## November 4: ToolHive first pipelines retain a successful compile and failed audit

[Actual results](../../reports/toolkit-v2/c13/toolhive-native-build-20261104/RESULTS.md) retain the source/dependency acquisition pass,
actual native boundary/version pass and successful compile. Go reordered21 cache
metadata JSON files; the post-build byte guard failed afterward. Exact original
hashes are recoverable without value changes; no source/ZIP/module bytes changed.
The2-operation acquisition and4-operation native costs remain settled. No ToolHive
program, MCP lifecycle, model or comparative trial ran. The corrected audit and
immutable artifact preservation require actual repeat approval; the existing binary
will be reused without recompilation. Langfuse2a0abaf4 also awaits repeat approval.
No passed docs/wheel/source pipeline is repeated. All-stack and both domain
journeys remain open. First new independent work remains delegated.
<!-- toolhive-first-pipelines-20261104:end -->

<!-- waza-native-preparation-20261104:start -->
**November 4: native Waza/Copilot artifacts and first backend bootstrap passed; protected sign-in is next.**
The new first-attempt pipelines used exact standing-authority reviews b9897f6b
and 87cc0c41. Two publisher-hash archives and all three regular files are retained.
Native containment, Waza static Go provenance and actual Copilot 1.0.85 version/help
passed. The Waza binary embeds pinned e534d149 but reports vcs.modified=true;
release/hash provenance is not exact clean-source build reproduction. Waza itself
has not run a real backend task. No models, provider credentials, Docker resources,
old tests or successful source/wheel/docs checks were used or replayed.

Canonical costs settled 2 ops/0models/6.269825874827802seconds and 5 ops/0models/
3.513753082603216seconds in the existing ledger. Wrapper time excludes children.
Preparation overhead is NOT_RECORDED;CPU, memory, wire bytes and cash are unknown.
Review counters were not reset. Host usable space remains above 50 GiB.
Read reports/toolkit-v2/c13/waza-native-backend-20261104/RESULTS.md.

GitHub now lists Copilot CLI in Free, with no credit card required. Earlier
paid-only assumptions were too broad; actual account eligibility remains unknown.
The concrete OPERATOR_SETUP.md links the terminal-only login helper and exact
review dd60853d. Neither helper nor its one-operation grant has executed; the
private credential directory is not created. Only the human operator may sign in.
Never capture sign-in or enumerate/hash/copy credential contents afterward.

Actual intervention pending: Langfuse repeat 2a0abaf4, ToolHive post-build repeat
1da90882, and protected Copilot setup. No compiler rerun is proposed. The current
public source pins, historical charges, Docker resources and user work remain.
Continue independent safe stack work; both SkillsBench domains and all required
integrations must pass before comparisons resume. No usefulness, resource or
release gate is closed. Product source 5a13a630 is unchanged. Parent ef7124c.
The new progress/setup prose is outside the passed docs snapshot; no current
docs-check pass is claimed for those edits. Group its next check with an
approved repeat rather than replaying the completed docs pipeline.
<!-- waza-native-preparation-20261104:end -->

<!-- approved-corrections-results-20261104:start -->
**November 4: ToolHive post-build checks passed; Langfuse cleared identity but failed Compose validation; Waza sign-in is deferred.**
The operator approved reviews1da90882 and2a0abaf4, and asked to postpone protected
Waza setup until a real backend check requires it. Exact replies are recorded in
each approval file and waza-native-backend-20261104/OPERATOR_DEFERRAL_20261104.json.

ToolHive's existing binary passed audit,actual version/help and build provenance.
All1,264 original artifacts are preserved with exact hashes,including21 restored
JSON encodings. No recompile/download occurred. Native grant9ops/0models/
90.18843654170632seconds retains the old4charges; preservation1op/0models/
0.7585593750700355seconds is separately settled. MCP lifecycle remains open.

Langfuse passed the repaired OCI fixtures and actual image/reference/layer checks.
Compose configuration validation then exited nonzero before any service resource
was created or started. The service grant13ops/0models/1.335084417834878seconds
retains all earlier charges; accounting/cleanup are resolved. Static inspection
found tmpfs mappings where Compose requires a string/list. The exact corrected
review is under langfuse-tmpfs-correction-20261104. Its first-party shape checks
pass; actual service execution remains unstarted pending specific repeat approval.

Waza sign-in must not run or be requested again while independent work can
continue. Its terminal-only helper/grant remain unapplied; no auth directory or
model call was created. New ToolHive/MCP lifecycle work remains eligible under
standing first-attempt authority. Both full domain workflows and all integrations
must pass before comparisons resume. Passed source,wheel,docs checks are reused;
new progress prose is outside the earlier docs snapshot. Parent3f10631.
<!-- approved-corrections-results-20261104:end -->

<!-- mcp-packaging-result-20261104:start -->
**November 4: both approved corrections ran; two concrete runtime repeats now need approval. Waza sign-in stays deferred.**
ToolHive review 1da90882 passed retained-binary audit/version/help without a build
or download. Langfuse review 2a0abaf4 passed image identity, then failed Compose
validation before startup. Its corrected temporary-mount review is
2dede925b424091d4fddb55666bd8fbd9105829a2b4eecc906c11ff63b0b1b9b.
No service retry has executed. All 13 Langfuse operations remain settled.

Independent ToolHive MCP review 9bad9397 ran its first attempt under standing
authority. The parent/name checks passed, but the legacy builder rejected my
COPY --chmod instruction. Read-only inspection found no owned output image,
container, network or volume. No MCP controller/server/client check ran. Its
five operations / zero models / 0.5746463751420379 seconds remain settled.
No shared accounting or cleanup uncertainty remains.

The portable-COPY correction is prepared at
reports/toolkit-v2/c13/toolhive-mcp-packaging-correction-20261104/operation-review.json,
SHA-256 96552b4eece46a4c56cdfbc29e05f024223ae8a7b67781e9dbb19cb98d37d542.
It preserves file bytes/mode, parent, binary, permissions and existing charges.
It adds no package, download, pull, plugin or installation. Its single build and
still-unstarted MCP lifecycle require exact approval under the repeat rule.
Both reviews preserve old Docker resources, user work and the 50 GiB reserve.

Do not run or request Waza sign-in while independent work remains eligible. The
operator explicitly deferred it; no provider credentials or model calls were
used. Product source 5a13a630 and its passed source/wheel checks are unchanged.
New operator scripts have syntax, model and static preparation checks; no passed
source, wheel or docs pipeline was replayed. New prose is outside the prior docs
snapshot. Both full domain journeys and all integrations remain open; comparisons
stay paused. Candidate usefulness, selection usefulness, resources and release
remain separate. Parent 0b01262.
<!-- mcp-packaging-result-20261104:end -->

<!-- runtime-diagnosis-results-20261104:start -->
**November 4: approved retries ran; ClickHouse startup and a ToolHive record-path defect are now diagnosed. Waza remains deferred.**
The operator's “Continue” approved the two exact pending reviews 2dede925 and
96552b4e. Both approval records preserve that context and forbid automatic retry.

Langfuse passed Compose validation and started the datastore phase. ClickHouse
failed while requesting 512 background scheduler threads under the 256-PID cap.
Read-only health and file audits retained only hashes and bounded diagnostics;
PostgreSQL, Redis and Minio health logs contain successful probes. All five owned
containers are stopped; their volumes, network, keys and images remain. No
web/worker or receipt export ran. Its grant now has 31 operations / zero models /
64.60480687581003 seconds, with settled accounting and cleanup.

The prepared small-workload pool correction keeps PID 256 and the same images,
uses one readonly XML fragment and a new owned namespace, and preserves all old
state. Its exact review is 62d7049b8f0962feac1546d2e751599777994ff2a9580ba3ccc40d9afc869ae1.
A fresh service/ingestion attempt remains unstarted and needs repeat approval.
The pool values are engineering proposals for one receipt, not production budgets.

ToolHive's portable-COPY image build passed and is retained as image 3c0b4f87.
The following build-record write referenced the wrong source location and stopped
before controller/profile/MCP execution. Its 11 operations / zero models /
8.105458749458194 seconds remain charged and settled. A retained-image continuation
fixes the source path and adds input preflight. Five preparation fixtures pass;
actual upstream lifecycle remains open. Exact review: 7ce23fdccd090ccbda424a2f957ce064f666b24a773bc5cf29e8519ee6c2e05c.
It performs no rebuild, download or installation and keeps the original ceiling.

Both corrected runtime attempts await actual approval under the repeat rule.
New first-attempt read-only diagnostics were covered by standing authority.
Waza sign-in remains explicitly deferred; do not request or run it now. Product
source 5a13a630 is unchanged. No passed source/wheel/docs/build/info/audit check
was replayed. New progress prose is outside the old docs snapshot. Both domain
journeys and the complete stack remain open; comparisons stay paused. Parent
137caed. Preserve unrelated CI edits and all SQLite/.aeep/private runtime state.
<!-- runtime-diagnosis-results-20261104:end -->

### Retain both terminal runtime attempts

Langfuse and ToolHive each reached a different runtime prerequisite after the
approved corrections. Keep the terminal receipts and their charges. The next
Langfuse attempt changes one merge-pool setting and uses an unused namespace.
The next ToolHive attempt explicitly reviews a fixed-port sandbox change and
checks its actual listener before invocation. Keep both integrations blocked
until actual lifecycle evidence passes. The repeat rule applies independently.

### Preserve the passing lifecycle scope

ToolHive's reviewed formatter journey passed and retains its reusable binary
and image. The optional Router executed its existing data fixture through
the installed CLI. Preserve both results as component evidence. Keep the
upstream MCP task checks and full composed workload checks separate.

Langfuse passed datastore startup after the merge-pool correction. A new web
heap failure requires one specific operator-approved repeat. Preserve the
stopped resources and charged operations.

### Reuse the checked funding declaration and published task environments

Keep developer support in the existing export preview with explicit source
disclosure and an exact review of the pinned funding file. Preserve the
legacy developer assertion and the separate trust labels.

Consider the exact upstream SkillsBench images before rebuilding dependency
closures. The selected source trees match except for newer instructions.
Use the original instructions and protected verifier for the pinned task.
Rights, hidden skill exclusion and reference behavior need their own checks.

### Verify complete dependency descriptors before protected task execution

Treat Maven's offline tree as partial until every selected artifact has
both its descriptor and binary. The first Spring solver reached
compilation with missing Jakarta, JPA and servlet dependencies. The
[diagnosis](../../reports/toolkit-v2/c13/skillsbench-spring-descriptor-repair-20261105/diagnosis.json)
binds that failure and the nine missing descriptors. Use the reviewed
resolver repair before preparing a solver repeat.

Preserve the Postgres MCP 0.3.0 version. The publisher image supplies a
candidate for the unavailable PyPI dependency. Review the actual bundled
runtime before using the server in a fresh owned database. Retain the
separate original verifiers and count each pack's readiness separately.

### Bound the Spring verifier with observed workload evidence

The [ordinary CLI preparation](../../reports/toolkit-v2/c13/skillsbench-ordinary-cli-preparation-20261105/README.md)
records a 42.97-second protected Spring grader command. The current
executable recipe caps a command at 30 seconds. Review a compatible
grading path with the original assertions before enabling that
configuration. Keep the task's binary score and the prior protected
reference results at their recorded scope.

### Retain the passing PostgreSQL reference scopes

Use the [passing MCP evidence](../../reports/toolkit-v2/c13/mcp-postgres-reference-results-20261105/README.md)
for the exact two reference-task checks. Keep their distinct databases
and upstream verifiers bound. Preserve the shared SQL derivation, the
withdrawn review and all original charges. Keep comparative dispatch
paused until the full stack gate passes.

### Separate packaged grading from model-backed workload proof

Retain both [passing packaged grader results](../../reports/toolkit-v2/c13/skillsbench-contained-graders-20261105/README.md).
Integration calibration uses its reviewed task cases and protected
reference without duplicating the case archive in extra literals.
Keep the legacy fixture minimums and formal case thresholds.
A separate worker closure and reviewed dispatch are required for each
ordinary CLI journey. For [Langfuse](../../reports/toolkit-v2/c13/langfuse-static-redis-20261105/README.md),
isolate the connection failure before another complete repeat.

### Reconcile private trace ingestion without replay

Retain the [failed export and successful readback](../../reports/toolkit-v2/c13/langfuse-ingestion-readback-20261105/README.md)
as separate observations. The original transport failure stays
terminal. Readback matched the exact canonical receipt and
disablement left the POST count unchanged. Keep this evidence
scoped to the exact installed exporter and private deployment.

### Keep SkillRank's upstream callback bounded

Use the [pinned upstream core callback](../../reports/toolkit-v2/c13/skillrank-callback-proof-20261105/README.md)
for the forced diagnostic. The AEEP parent owns worker execution,
protected grading and accounting. Keep upstream compatibility
defaults out of measurements. The synthetic proof does not
authorize a live run or supply candidate usefulness evidence.

## D164. Keep SkillRank's required-use pair within an engineering plan

Use the same reviewed coordinator and canonical trial runner as ASE.
V9 adds exactly one fresh control and treatment, with an engineering
review and a pinned read-only native SkillRank carrier. Only protected
grade certificates cross the scheduler boundary. The one-route v8 ASE
contract remains in effect. A real native synthetic check is recorded
separately from any future controlled-worker run.

[Native carrier and limitations](../../reports/toolkit-v2/c13/skillrank-native-carrier-20261105/README.md).

## D165. Preserve SkillsBench asset gates after image acquisition

Record image and embedded-input identity independently from rights to
execute, disclose or redistribute those assets. Financial Modeling QA
has a matched third-party source and an unresolved rights record.
Invoice Fraud Detection is a proposed hard same-revision replacement.
Keep the original selection until the operator approves a change.

The AFlow lock remains unchanged. Use the retained Linux ARM64
CPython 3.12 target for the reviewed wheel closure and protect the
generated-code and grading boundary before running its optimizer.

## D166. Use Invoice Fraud for the local document/data integration

The operator approved the hard same-revision replacement after asset
and runtime review. The [asset and acquisition record](../../reports/toolkit-v2/c13/skillsbench-invoice-fraud-20261106/README.md)
binds the original fixtures and Apache-2.0 notice. Use the retained
image and keep the original verifier and ground truth outside workers.
Financial Modeling QA stays parked pending a rights record. Provider
disclosure and model dispatch remain separate approvals.

Keep the two terminal AFlow boundary failures and their charges. The next
review measures the retained runtime's interface and route counts before
upstream import. It keeps the pinned image and offline policy. A successful
import or graph parse still leaves finite calibration open.

## D167. Verify the optimizer's socket boundary before loading AFlow

Keep Docker network isolation and the non-root read-only runtime. The
[reviewed Moby profile](../../reports/toolkit-v2/c13/proposal-optimizer-preparation-20261105/socket-boundary/profile-source.json)
removes socket-related permissions from the daemon's pinned default.
The guest checks socket denial, inherited descriptors and routing before
importing AFlow. Keep this evidence scoped to import and parsing. A finite
protected calibration still needs a separate review.

The [Invoice Fraud pack](../../reports/toolkit-v2/c13/skillsbench-invoice-fraud-20261106/task-pack.json)
keeps its binary upstream reward and protected assets. A local rights draft
cannot authorize provider disclosure.

## D168. Keep the EvoAgentX proposal behind a single reviewed relay

Use the real upstream planner and graph builder from the retained
[proposal-only image](../../reports/toolkit-v2/c13/evoagentx-distribution-20261106/proposal-runtime/evoagentx-runtime-result.json).
Freeze the [request digest](../../reports/toolkit-v2/c13/evoagentx-distribution-20261106/planner-handoff/result.json)
before reviewing disclosure. The reply path admits only the reviewed JSON
nodes and ports before the upstream parser sees them. Pass the normalized
graph to the existing AEEP stack planner as an inert proposal. Keep
provider authority and stack execution authority separate.

## D169. Validate the actual proposal reply on the existing managed grant

Use one exact Codex worker turn on the existing onboarding grant. Bind
the real planner's captured public request and the final provider text
digest. Use the existing paired worker and collector checks and the
candidate-absent control route. Keep the retained worker profile. The
prompt forbids tool use and any recorded tool activity rejects the reply.
Store reply and graph evidence as hashes and inert references.

The [exact operation review](../../reports/toolkit-v2/c13/evoagentx-distribution-20261106/managed-turn/operation-review.json)
requires separate disclosure and execution approval. Close the proxy
and retain the ledger after the single attempt.

## D170. Reconcile a terminal turn from its receipts

Preserve the terminal EvoAgentX driver and settlement records. Recover
the result through a [read-only audit](../../reports/toolkit-v2/c13/evoagentx-distribution-20261106/managed-turn/audit-settled-turn.py)
when report serialization fails after settlement. The worker and
validator receipts distinguish a successful actual reply from a missing
summary. Do not spend another turn to reproduce that summary.

AFlow's protected grader stores only the score and case outcomes in its
public integration record. The optimizer receives the existing grade
digest and aggregate score. The [bounded continuation](../../reports/toolkit-v2/c13/proposal-optimizer-preparation-20261105/calibration/optimizer-directory-correction/operation-review.json)
reuses the grade and stops at the first formatted proposal request.
Provider dispatch and generated-code execution require separate scope.

## D171. Keep the approved document substitute and an independent reference

Use `exceltable-in-ppt` at the same SkillsBench revision. The
[asset review](../../reports/toolkit-v2/c13/skillsbench-document-substitute-20261106/selection-and-oracle-rights.json)
traces the vendor helpers to restricted bundled skills. Use the
independent OOXML reference to calibrate the original eight verifier
assertions. Keep the original inputs and binary reward. Only the
instruction and input deck enter the agent archive.

The [AFlow bounded cycle](../../reports/toolkit-v2/c13/proposal-optimizer-preparation-20261105/calibration/finite-cycle/result.json)
uses the original optimizer and formatter with two reviewed workflow
choices. A managed reply can select a policy. It cannot supply executable
code, new prompts, protected labels or additional model turns.

## D172. Reuse the document workers and keep reference outputs protected

The [approved local rights](../../reports/toolkit-v2/c13/skillsbench-document-rights-20261106/result.json)
allow exact task preparation. Managed execution retains a separate gate.
Use the existing capable Sales image pair for each document task, with
an explicit output filename and byte limit. Keep the recovered Invoice
Fraud reference and the independent Excel reference in private recipes.

Preserve the upstream RapidFuzz version. The [download retry](../../reports/toolkit-v2/c13/skillsbench-document-managed-20261106/rapidfuzz-continuation-review.json)
changes the license guard, without substituting another version.
The [Excel build retry](../../reports/toolkit-v2/c13/skillsbench-document-managed-20261106/excel-build-continuation/build-review.json)
reuses the retained Buildx client profile and the unchanged COPY-only
context. Both terminal first attempts and their charges remain.

## D173. Bind the packaged graders and retain the React solver result

The [document grader proof](../../reports/toolkit-v2/c13/skillsbench-document-managed-20261106/packaged-grading/grader-execution/summary.json)
passes on the two pinned images through the ordinary container executor.
Use those images with the two exact reviewed task archives. The next
[managed review](../../reports/toolkit-v2/c13/skillsbench-document-managed-20261106/managed-engineering/operation-review.json)
keeps the grant limits and expiry unchanged and requires both plans to
pass before a model sees public inputs.

The [React reference](../../reports/toolkit-v2/c13/skillsbench-react-reference-20261106/result.json) reached its verifier after
the pinned solver exited successfully. Prepare the verifier retry from
the seven exact source edits in the solver. Bind the installed pytest
plugins and retain all eleven original assertions and their thresholds.

## D174. Preserve the trial when a workflow summary fails

Reconcile the [Invoice trial](../../reports/toolkit-v2/c13/skillsbench-document-managed-20261106/managed-engineering/invoice-reconciliation.json)
from its canonical receipt, protected grade and ordinary CLI report.
A completed task can score zero. A wrapper failure after settlement
cannot invalidate that grade or authorize another turn. The audit uses
normalized receipt references and compares timing to the canonical trial.

For React, derive the exact expected browser parameter IDs from the
[retained plugin](../../reports/toolkit-v2/c13/skillsbench-react-reference-20261106/browser-id-continuation/browser-id-proof.json).
Preserve the solver edits, eleven protected checks, offline boundary and
binary reward. Keep the rejected receipt as part of the execution history.

## D175. Bind SkillRank certificate timing in the scheduler definition

The [timing audit](../../reports/toolkit-v2/c13/skillrank-native-carrier-20261105/managed-callback-deadline-audit.json)
found a completed managed task whose agent time exceeded the old certificate
window before protected grading. Accept a finite, explicitly reviewed deadline
for the two SkillRank slots and keep both inside the command timeout. Preserve
the old default and serialized digest. The [native repeat](../../reports/toolkit-v2/c13/skillrank-certificate-deadline-20261107/operation-review.json)
uses the same upstream revision and Cargo lock. It checks the revised bridge
with synthetic grades before considering a separate managed diagnostic.

## D176. Bind only the public React archive for managed preparation

Use the [pinned React pack](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/react-pack.json)
for the original instruction and website inputs. Keep the simulator,
solver patches, protected verifier and bundled skills outside the
archive. The reference and two control receipts bind the same eleven
upstream assertions. The [asset-use review](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/operation-review.json)
allows local registration after approval. It gives no authority for
provider transfer or a model turn.

Reuse the [verified ARM64 SkillRank binary](../../reports/toolkit-v2/c13/skillrank-certificate-deadline-20261107/result.json)
for a future two-slot diagnostic. The [prepared carrier](../../reports/toolkit-v2/c13/skillrank-managed-diagnostic-20261107/carrier-preparation.json)
binds the fresh owned workspace and 120-second certificate window.
Keep worker review and managed dispatch authority separate.

## D177. Size the protected React scratch mount from a measured run

The [nonroot reference](../../reports/toolkit-v2/c13/skillsbench-react-nonroot-calibration-20261108/result.json)
passed the same eleven assertions and used up to 111.3 MiB of scratch
in 50 ms samples. Use 160 MiB for the next reviewed carrier check. Keep
32 MiB for legacy environments and the existing default shared memory.
A single observation does not establish production resource acceptance.

Keep the original AMD64 image. Reuse the archived browser bytes and
the prior Python dependency versions. The six platform wheels stay
separate from the protected reference patches. The
[ordinary runtime review](../../reports/toolkit-v2/c13/skillsbench-react-ordinary-carrier-20261108/runtime-review.json)
binds one offline COPY-only build and four output cases.

## D178. Use the original React image with pinned read-only grader mounts

The [export observation](../../reports/toolkit-v2/c13/skillsbench-react-readonly-grader-20261108/export-observation.json)
records the failed lazy-layer fetch and the tag left behind. Preserve
both tags and the settled operations. Use the original calibrated
image through the ordinary container executor. Mount the reviewed
Chromium, Python dependencies and protected verifier read-only.
The new wrapper changes only those paths. Keep the protected tests
and score semantics unchanged and keep reference patches outside the
runtime mounts. The [grader-only review](../../reports/toolkit-v2/c13/skillsbench-react-readonly-grader-20261108/operation-review.json)
requires approval before dispatch and leaves the managed task separate.

## D179. Verify the managed React payload separately from the protected grader

Keep the [verified AMD64 grader](../../reports/toolkit-v2/c13/skillsbench-react-readonly-grader-20261108/result.json) separate
from the managed ARM64 workers. Resolve only the platform-appropriate
packages from the task lockfile and preserve their bundled notices.
The [image parity audit](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/worker-image-parity.json)
binds the package bytes and permissions. The worker smoke checks use
the public project and the existing Node runtime. The protected
simulator remains available only to grading.

The first managed preparation selected the wrong benchmark. The
[corrected review](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/managed-continuation-review.json)
binds the React pack, recipe, task IDs and validated existing worker
boundaries. Keep the stopped attempt and its accounting. Dispatch
requires exact authority and evidence from the ordinary CLI.

## D180. Package React's grader without extra host roots

The [canonical plan](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/managed-continuation-ready.json)
prepared successfully. The [recipe boundary](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/managed-carrier-boundary.json)
rejected the mounted grader before any model turn. Keep the product
guard. Package the reviewed assets into the self-contained AMD64 image
using the filesystem from the verified original container. The
[approved checks](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/self-contained-result.json) exercised
the real reference and the seven grade payloads before approving a
new managed plan. Keep both stopped plans and their charges.

## D181. Pin the unstarted React turn to GPT-6.1 Sol

The operator selected GPT-6.1 Sol. Preserve medium reasoning, the
same worker images and the verified grader. The
[Sol review](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-managed-review.json) requires both
workers to resolve the exact model through the existing Codex
destination before the ordinary workflow can dispatch. Keep Astra
receipts under their original identities. No model fallback is enabled.
[OpenAI model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

## D182. Check the client catalogue before Sol dispatch

The [approved 0.154.0 worker check](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-managed-model-blocker.json)
could not select GPT-6.1 Sol, so it spent no model turn. Retain both
prior workers. The [refresh review](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-client-worker-review.json)
uses a versioned path for the verified CLI 0.159.1 package and checks
the bundled catalogue with an empty home and no network. Treat any
authenticated model availability as a separate observation.
[OpenAI changelog](https://learn.chatgpt.com/docs/changelog).

## D183. Bind the verified Sol client for managed React checks

The [offline worker refresh](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-client-worker-result.json)
verified the bundled Sol catalogue on both new image digests.
Retain the prior workers. The [managed review](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-01591-live-20261109/operation-review.json)
pins the new client path, binary hash and App Server version. It uses
the existing proxy, isolated workers, public inputs and verified
grader. The grant amendment changes expiry only. Require a fresh
account-backed model identity and both boundary checks before
dispatch.

## D184. Diagnose the refreshed worker without a provider session

The [managed inspection](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-01591-live-20261109/sol-managed-sandbox-blocker.json)
resolved the requested model and stopped at the sandbox command.
Keep the control and treatment bindings, and preserve the strict
readiness gate. Use the [offline diagnostic](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-sandbox-offline-20261109/operation-review.json)
to capture a bounded exit code and fixed error categories from the
same command. An offline result cannot attest to account-backed worker
conformance. Approval is required for the repeat.

## D185. Put the refreshed client inside the existing read root

The [offline diagnostic](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-sandbox-offline-20261109/result.json) reproduced the
Bubblewrap failure. The [pinned Codex implementation](https://github.com/openai/codex/blob/rust-v0.159.1/codex-rs/linux-sandbox/src/linux_run_main.rs#L1539)
re-executes the current client inside the sandbox. The
[control image](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-sandbox-path-20261109/result.json) restored command startup by
placing the same bytes within `/opt/codex`. It kept the sandbox policy.
The [candidate-only continuation](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-sandbox-candidate-20261109/operation-review.json)
retains the control and all historical charges.

## D186. Use Prefix Cache Replay in the third software slot

The original Dependency Audit database lacks a verified rights record.
The [approved replacement](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/selection.json) uses the same
SkillsBench revision. Its committed trace matches the published Mooncake
prefix byte for byte. Keep the upstream grading semantics and both
license notices. Preserve the Dependency Audit history. Provider
disclosure requires separate authority.

## D187. Recover the completed React observation without a replay

The [canonical report](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-permitted-path-live-20261109/report.html) was written during the
ordinary CLI run. The follow-on wrapper attempted to read obsolete
normalized fields. Keep that terminal result and its charges. The
[read-only audit](../../reports/toolkit-v2/c13/skillsbench-react-managed-preparation-20261107/sol-permitted-path-live-20261109/completed-run-audit.json) verifies the
settled task, receipt and usage without invoking a worker. Its scope
is the required-use engineering journey.

## D188. Reuse the known Python support for Prefix Cache Replay

The [first-party canary](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/bootstrap/result.json) identified
the missing Pydantic import before any task code ran. The
[correction](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/runtime-support/operation-review.json) binds
the exact support tree already used with the same grader image.
It keeps the original solver, assertions, input bytes and sandbox.

## D189. Preserve the Prefix Cache infrastructure observation

The approved [runtime correction](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/runtime-support/operation-review.json)
needed a [coordinator binding fix](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/runtime-support/dispatch-binding.json)
before its first reservation. Keep the original approved workload and
receipts. The [read-only audit](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/runtime-support/audit.json) verifies
that omitting the trace errored all nine dependent checks and left the
independent consistency check passing. No grade was issued. Keep the
failed driver result and use the retained evidence without replay.

## D190. Package the Prefix Cache grader as a local image layer

The managed recipe requires a pinned offline container without extra
host roots. The [draft](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/managed-preparation/carrier-preflight.json) adds only
the protected task files and pinned Pytest closure to the retained
nonroot React grader image. Use the existing binary grading contract.
Run the reference and canonical grader checks on the resulting image
before requesting a model turn. The build waits for the host reserve.

## D191. Bind the first Prefix Cache build to the updated local Docker tools

The [offline review](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/managed-preparation/carrier-verification/operation-review.json)
pins the observed Docker and Buildx binaries after verifying their signatures.
Keep the existing pinned parent image, protected task bytes and verifier.
Use the standard containment executor and receipt ledger for the first local
build and grader checks. Wait for measured usable disk space before launch.

## D192. Base Prefix Cache launch on measured usable storage

The [verified cleanup](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/managed-preparation/carrier-verification/cleanup-result.json)
removed the authorized worker copies. The measured free space stayed
below the launch requirement. Retain the existing backups and Docker
resources. Use the current filesystem reading for the build decision.

## D193. Keep local restore points during storage recovery

The [APFS audit](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/managed-preparation/carrier-verification/apfs-reclaim-audit.json) found pre-cleanup Time Machine
snapshots. Retain those restore points. Use measured free bytes
after normal reclamation or an operator-managed space change.

## D194. Retain the verified protected Prefix Cache image

The [execution audit](../../reports/toolkit-v2/c13/skillsbench-software-substitute-20261109/managed-preparation/carrier-verification/execution-audit.json)
confirms the pinned parent, added task layer and settled grader receipts.
Use that image for managed workflow binding and keep the sealed grader
outside the model workers. Provider disclosure and the managed task turn
still require their own authority.
