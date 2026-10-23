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
