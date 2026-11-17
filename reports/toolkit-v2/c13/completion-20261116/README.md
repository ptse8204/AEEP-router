# C13 beta handoff and remaining evidence

## November 17 handoff

The current [formal document verification](formal-document-native-verification.json)
binds commit `d985f2f4`. A private ledger copy accepted all 37 required
checks on tracked source `03c615b3`. The operational ledger retains its
original execution bindings. The ordinary CLI accepted a 141-case fixture,
and the public artifact adapter matched three retained CFPB inputs. The Audent
ExtractBench reference calibration now passes. Both workspace suites passed 2,181 tests
with 21 skips. Both branch coverage gates and all 72 offline docs checks passed.

Wheel `d5f092a8` passed archive inspection. The installed lifecycle evidence
below covers the earlier wheels identified in that section. Private beta
use on the reviewed macOS runtime remains LIMITED_BETA. Candidate
usefulness and AEEP selection usefulness still need separate formal
evidence. Production release and public benefit claims remain NO_GO.

### CFPB native task-pack checks

The [local component result](cfpb-local-component-result-20261117.json)
verifies the three CFPB references and their empty-output controls using
the retained image `aeep-extractbench:cfpb-canonical-local-20261117`
(`sha256:c047c726a98ebeae08626ae2123280a62b026bba4469a968a47c2be2e6e17f14`).

| CFPB task | Reference F1 | Empty-output F1 | Empty-output verdict |
| --- | ---: | ---: | --- |
| H25F | 1.000000 | 0.730769 | Rejected |
| Filled sample | 1.000000 | 0.005556 | Rejected |
| H25E | 1.000000 | 0.020833 | Rejected |

The upstream scorer credits matching blank fields. Its perfect-match
rule still rejects all three empty submissions. The driver incorrectly
expected every empty output to score zero; its mismatch flags and failed
receipt statuses remain. The [read-only audit](audit_cfpb_component_result.py)
checks the actual certificates against the unchanged upstream rule.
It preserves native scores and requires no verifier replay.

A storage stop followed the settled build and first reference. Only the
five unstarted roles continued, inheriting both earlier operations and
their charges. All seven settled at 26.449 seconds against 425 reserved;
all owned containers are absent. These are three related tasks in one
source family, with zero formal cases adopted. Provider disclosure and
the full managed CLI journey remain unapproved and unexecuted.

The [current-wheel check](current-wheel-repeat-preflight-20261117.json)
is prepared for wheel `d5f092a8` and 32 unchanged cached dependencies.
Nine full-driver scenarios and four sandbox checks pass. Exact repeat
`f47bbb55` needs approval and 52 GiB usable space before installation.
The seven phases cover install, idempotence, source identity, candidate
inspection, HTML/Markdown reporting and removal of only the unchanged
new test runtime. Existing runtimes and journals remain.

The [cleanup record](verified-pytest-cleanup-result-20261117.json) accounts
for 3,904 obsolete pytest worker copies, about 4.58 GiB allocated. All
74 final preservation hashes match. No backups or Docker resources were
removed. Current usable space is recorded separately from allocated bytes
removed. Waza remains excluded and comparisons stay paused.

### Approved work and next decision

[Correction group `3376c129`](correction-group-3376c129-result.json) completed
all five operations in 9.048 seconds against 490 reserved seconds.
All charges settled, and owned-container cleanup passed. The
[software correction](software-correction-result-20261117.json) completes
the five protected reference/original pairs from the earlier group.

| Software case | Reference | Original | Scope |
| --- | --- | --- | --- |
| py3status | 1/1, two tests passed | 0/1, one test failed | Original protected pair |
| Sentry | 1/1, 41 tests passed | 0/1, one test failed | Original protected pair |
| Hugging Face Hub | 1/1, 21 tests passed | 0/1, two tests failed | Original protected pair |
| py-fsrs | 1/1, 34 tests passed | 0/1, two tests failed | Original score recovered from the retained diagnostic |
| Files-to-prompt | 1/1, 18 tests passed | 0/1, five tests failed | Exact compatible Click 8.1.8 |

Py-fsrs's two failures include the published lazy-loading regression and the
authored preservation guard. The earlier review expected only the guard
to fail. The unchanged ordinary grader accepts the actual complete test
dispositions and returns `test_failure`. Read-only recovery retains the
earlier strict-contract mismatch and avoids another upstream invocation.

The [native ExtractBench calibration](extractbench-native-calibration-result-20261117.json)
passed on the unchanged Audent task. The worker verified the exact 70
distributions, 7,613 files, four native import origins, read-only dependencies
and scratch `noexec`. One operation settled at 16.026 seconds. The
existing recipe response normalizer preserved the real fractional scores
and refused to turn a missing reference into a task score.

| Calibration condition | Native value F1 | Disposition |
| --- | ---: | --- |
| Reference | 1.000000 | Exact success |
| Changed value | 0.998538 | Inexact |
| Missing row | 0.990406 | Inexact |
| Repeated row | 0.991228 | Inexact |
| Malformed output | 0.000000 | Invalid submission |
| Missing output | 0.000000 | Invalid submission |
| Missing reference | Unknown | Infrastructure error |

These seven conditions belong to one calibration task. The same dependency
versions now load from their retained read-only path. The recorded
pre-dispatch refinement replaced an absent `regex` probe with already locked
`lxml`, with a static membership check and no extra attempt. Both original
operator approval and the refinement are bound in the calibration result.

The [CFPB route audit](../../../../.aeep/completion-20261116/cfpb-runtime-route-audit-20261117/route-audit.json)
confirmed that canonical recipe invocation rejects extra host roots before
reservation. The completed local checks above use the self-contained
COPY-only image of the existing dependencies and protected context. Full
managed workflow preparation also checks provider-disclosure rights, which
remain unapproved for these CFPB inputs.

Earlier cleanup authorization covered verified obsolete pytest worker
database copies. Removing 2,688 such copies reclaimed about 3.2 GiB of
allocated storage. All 70 preservation hashes matched, including primary
fixture databases, inputs and logs. The reviewed launch floor was restored for that completed group.
The [cleanup receipts](correction-group-3376c129-result.json) retain exact
paths and measured free-space changes.

Waza remains excluded and comparisons stay paused. These protected
reference checks leave formal assignment, candidate usefulness and
selection usefulness open. [Earlier group results](offline-group-result-20261117.json)
retain the original source recovery and failed grader outcomes.

The [verified projection bindings](verified-publisher-projection-bindings.json)
connect all five publisher proofs to the original staged task inputs,
protected overlays, editable paths and 129 required test identities. Both
reference and original payload hashes reproduce through the ordinary callback
with first-party replies. Twenty altered source and payload bindings were
rejected. Actual protected runtime grading remains open.

The [source recovery driver](check_expansion_tree_recovery.py) binds five
retained archives. Three contain Git submodule declarations. The exact
review `7e9158ba` uses at most eight GitHub metadata requests and reconstructs
the publisher tree with Git submodule pointers. It does not download the
archives again or fetch submodule contents. Five bindings, six malformed
tree controls and a simulated matched recovery passed. The approved publisher
run and inverse-export proof now supply all five source bindings.

The [publisher reconciliation preflight](publisher-reconciliation-preflight.json)
bound the five staged projections to the exact metadata review. Its actual
read-only inspector reopened the retained Git trees, license hashes and
ordinary grader payloads. The newer projection bindings also accept MontePy's
inverse-export proof. The original fixture controls remain recorded.

The [retained source projections](retained-projection-staging-result.json)
stage the OpenAI Agents multi-file repair and the Ophyd Async contract
audit through the ordinary archive and grading interfaces. Both private
indexes reproduced byte for byte. The original OpenAI archive stays
intact. Its worker projection omits two hash-bound instruction files and
preserves both editable source paths and all 24 published test identities.
Ophyd Async keeps its 28 published identities and adds the protected
preservation check. Publisher binding is verified for both projections.
Their protected runtime reproduction remains pending.

The [retained link projections](retained-link-projection-result.json) stage
MontePy, GitPython, RETURNN and AiiDA Quantum ESPRESSO. They copy 27
hash-bound link targets into regular files and omit four MontePy directory
aliases under documentation or demos. RETURNN's existing bootstrap selects
the same repository root with the copies. All 129 published test identities
are preserved. Both preparations matched byte for byte. Publisher binding now
covers MontePy, GitPython and RETURNN. AiiDA needs a separate binding, and
protected grading remains open for all four.

The [retained runtime prerequisites](retained-runtime-prerequisites.json)
identify missing named wheel candidates for four projections. GitPython
also needs a compatible history fixture for its protected clone and tag
checks. The ordinary archive carries regular source files, and the
contained grader denies injected host environment variables. For RETURNN,
the existing ARM64 image ID and both ordinary grader payloads passed
preflight with all 13 identities. Its publisher binding is now verified.
Actual isolated runtime checks still need to settle.

The [staged runtime triage](repository-expansion-runtime-triage.json) checked
all 13 staged cases against the ordinary grader and retained wheel cache.
For Django Guardian, four wheel hashes, license notices and active
dependency declarations match the prior review. Its SQLite test
settings still require `django-environ`. LLM Sandbox's locked
`pydantic-core` wheel is available for Python 3.12 and lacks a matching
3.13 wheel in this cache. Its selected tests also reference backend
clients through mock targets. The OpenTelemetry case needs a verified
monorepo import projection so tests exercise the patched snapshot.
The other ten cases have unresolved declared dependency candidates.
No protected tests ran in this audit.

The [OpenTelemetry preparation](opentelemetry-monorepo-preparation.json)
preserves the public source and edit path. The protected overlay binds
the API, SDK, semantic conventions and test utility imports to their
original repository roots. It supplies metadata for 24 entry points from
the pinned project files. The lookup rejects an already loaded package
and a conflicting module path. Both ordinary callback payloads preserve
the 18 grading identities and match across two staging runs with
substituted replies. The three missing locked wheels total 62,028 bytes.
Actual contained results and formal adoption are pending.

The retained source queue has 111 unattempted repositories. If each
contributes one eligible case, all 116 current prospects qualify, and
all six retained projections clear review, the pool reaches 233.
Qualification and marginal value together require at least 246 distinct
inputs under the shared-early-case assumption. This scenario still needs
13 cases from further recovery or additional intake.

The [retained issue screen](retained-issue-overlap-screen.json) allows
additional issues within one repository split only where revision,
patch, production paths and issue test modules differ. It finds 154
leads in the 111 unattempted repositories. The recorded balanced profile
still needs 48 multi-file repairs beyond the 122 conditional prospects.
The unattempted queue has at most 26 matching path-shape leads. Screening
the older inventory and alternate revisions adds 20 supplemental leads,
including seven with retained archive files. At least two more multi-file
cases are needed in that optimistic scenario. Archive, scope, rights and
runtime still need independent verification.

The [supplemental archive recovery](supplemental-archive-recovery-result.json)
rechecked every retained copy for seven screened leads. Copier and
Pyinfra have complete copies with the recorded archive and license
hashes. Five other leads have truncated gzip files. Ordinary staging
keeps both edits, all 18 published test identities and the one-file
controls for Copier and Pyinfra. Both Unicode spellings of Copier's
fixture remain in the packed input. Publisher matching and protected
runtime reproduction still need to settle. The 20-lead count already
includes these two cases.

## Retained stack and lifecycle evidence

The operational ledger accepts all **37 required integration checks** for the
frozen execution source, including the ordinary CLI and canonical reports for
both workload domains. Waza is excluded by the operator. The CLI still rejects
a request that explicitly selects Waza without its two checks. It also rejects
the same completion record on a different source digest.
[Readiness audit](readiness-audit.json) · [Retained evidence](../managed-comparison-20261115/offline-evidence/source-stack-rebinding.json)

A [source compatibility audit](current-stack-source-binding.json) confirms
all 37 checks on committed source `9710ea4f`. The ordinary CLI accepted
completion `23c4b48e` in a private ledger copy. Selection conversion is the
only changed runtime file. Both workflow preparations produced new references
with their original observations intact. The old source reference, the
unreviewed completion and an explicit Waza selection were refused on the new
source. All 53 focused tests and the schema check passed. The audit read
the operational ledger without changing it. The newer wheel was checked
as an archive. The install and rollback evidence below covers the older
tested wheel. [Audit driver](rebind_current_stack.py)

**LIMITED_BETA** for private macOS arm64 / Python 3.13 evaluation work with the
reviewed runtime and documented controls. **NO_GO** for production release and
for public claims of better task results, reduced token use or cost savings.
C13 remains open. No release or automatic admission was performed.

| Function | Verified scope | Remaining limit |
| --- | --- | --- |
| agent-skill-eval and managed AEEP fallback | Actual controlled dispatch, protected grading, accounting and cleanup under explicitly chosen engines | No automatic fallback after a failed run or assumed Codex equivalence across native upstream backends |
| Ordinary CLI, SkillsBench and protected reports | Sales Pivot and Spring Boot bind setup, readiness, grading, reports and private trace verification. Six pack tasks have managed grades | Their grades show task outcomes. The journeys do not establish capability or selection value |
| SkillRank and Cisco Skill Scanner | Pinned search/show, bounded managed diagnostic, static scan, findings and analyzer-failure retention | SkillRank required-use evidence stays diagnostic. The scanner does not establish safety or benefit |
| ToolHive, MCPMark and MCP-Universe | Reviewed MCP launch/invoke/stop plus both protected reference-task journeys and state cleanup | Reviewed servers, tasks and permission scopes only |
| OpenTelemetry and Langfuse | Receipt-bound minimized export, private readback and disabled-export controls | No automatic remote export, prompt retention or cost measurement |
| LangGraph, Agent Framework, EvoAgentX and AFlow | Bounded composition/interruption, a validated upstream proposal, and a finite protected calibration cycle | No arbitrary execution of generated work or claim of optimizer benefit |
| Optional Router and GitHub Sponsors | Approved routing configuration, Essentials independence, source-bound attribution and support link | No admission, payment or public release authority |
| Retained Essentials wheel `82d8ed9c` | Installed and reapplied idempotently, source verified, sample candidate staged and both reports generated with network denied | Clean rollback passed in a fresh private root. The older Finder-interrupted residue and journal remain preserved |
| Supported hosts and operator use | macOS arm64 / Python 3.13 checks; earlier actual helped report comprehension | Wider host matrix and unassisted operation remain unverified |
| Waza | Historical evidence retained | Excluded from this delivery |

The [SkillsBench grade ledger](../canonical-stack-verification-20261113/skillsbench-ledger-audit.json)
includes three verified passes and three verified task failures. The latest
direct LibCST rerun has four 0/1 grades. The two Canopen arms passed 6/8
protected tests each and the two Xsdata arms passed 28/29 each. The observer
recorded no covered LibCST calls. Unsupported execution paths remain unknown.
The Sales follow-up and historical Ponytail comparisons retain their original
development or study scopes.
[Direct LibCST results](../managed-comparison-20261115/DIRECT_LIBCST_RERUN.md) ·
[Matched Sales follow-up](../managed-comparison-20261115/FOLLOWUP_RESULTS.md) ·
[Ponytail repository results](../repository-usefulness-pilot-20261029/README.md)

## Essentials install and rollback

The first macOS private install of wheel `82d8ed9c…` bound 198 package files to
the frozen source. It used 32 unchanged cached dependency wheels. The 33
archives total 15,479,784 bytes. The observed private runtime allocation was
84,602,880 bytes before removal. These figures exclude Docker, upstream runtime
caches, execution workspaces and retained evidence. There is no new whole-host
resource qualification or maintenance-cost estimate.

The ordinary `install-plan`, `install`, `candidate`, `report` and `remove`
commands used exact plan `99e47d4b…`. The installed CLI denied a test network
bind, an unrelated file read and an unrelated write. The candidate and report
are synthetic fixtures. No agent, grader, service, download or model ran.

After idempotent apply and reporting, `remove` detected three added Finder
files and preserved the runtime. The full tree matched the applied fingerprint
when those files were excluded from the **read-only diagnosis**. The three files
were moved byte-for-byte into a private evidence directory and the tree
fingerprint matched again. The second removal attempt left a `removing`
journal. The current residue has no installed package directory. The generic
CLI error does not identify where removal stopped. The fixture reports, journal
and preserved metadata remain available for recovery review. The clean rollback rehearsal binds the same wheel and dependency
closure to a fresh private root outside the Finder-observed tree. Approved
review `e04a7998` installed and removed the wheel with network denied. It
verified the new removal journal and preserved both the neighboring file and
the earlier interrupted residue and journal.
[Clean rollback result](macos-private-rollback-result.json) ·
[Wheel and lifecycle evidence](beta-package-audit.json) ·
[Installer controls](../../../../docs/aeep-toolkit/INSTALLATION_DESIGN.md#implemented-private-wheel-runtime)

The [Essentials preflight for wheel `b502bb84`](current-essentials-preflight.json)
binds wheel `b502bb84` and both 33-package closures. The macOS CLI
reproduced the exact install plan in a sandbox that denied outside reads
and writes and network binds. A wrong plan digest left the destination
absent. The source CLI reproduced the candidate identity and both
fixture report hashes. All 124 installer, candidate and reporting
tests passed. Linux preview used the earlier platform wheels and the
current core wheel. The guest has yet to check that closure at runtime.

The [native operation review `788373dc`](current-essentials-macos-operation-review.json)
covers one private install, a successful-plan reapply, installed source
and report checks, and one rollback. Seven substituted driver checks cover
terminal errors and refusal to replay. The ordinary install-plan and
sandbox probe ran before review. The actual lifecycle remains unstarted,
pending exact repeat approval.

## Retained runtime footprint

The [read-only inventory](retained-runtime-footprint.json) measured 17 image
IDs across selected accepted component proofs. Docker reports 18.36 GB
gross for those images. This sum includes shared layers. The retained
Langfuse namespace has five measured volumes and eight stopped containers.
The inventory also records four optional native runtime paths. Essentials
used 15.48 MB of wheel archives and 84.60 MB of allocated storage before
the first removal attempt. The current interrupted directory is residue
and is measured separately. Its installed package directory is absent.
[Docker disk usage definitions](https://docs.docker.com/reference/cli/docker/system/df/)

Setup and upkeep span the owned Python environments, pinned Docker images,
protected task assets, and optional Langfuse data. The inventory binds 18
component records and 37 accepted checks to their original evidence.
A changed source, runtime or permission must retain applicable verification.
Managed worker allocations, shared-layer usage, retained evidence and caches
are outside the measured totals. Maintainer time and production resource
capacity remain unmeasured.

The [assembled runtime audit](assembled-runtime-footprint.json) adds the
workers and graders from both accepted workflow plans and the accepted
evaluator and SkillRank runs. It reopens six original worker receipts.
All 25 configured image IDs were present. The gross Docker size was
28.01 GB. Counting 184 unpacked filesystem chains once gave 12.43 GB
of image history sizes. The five selected Langfuse volumes added
83.29 MB of exact daemon-reported volume data. Host allocation and
maintenance labor remain unknown.

The [resource observations](skillsbench-resource-observations.json) reconcile
all six completed SkillsBench commands to their original receipts and settled
charges. The full command span ends before the final receipt write and Router
close. The wrapper charges its exclusive wall time and process CPU after
excluding canonical execution.

| Integration task | CLI span | Exclusive wrapper | Agent | Protected grading |
| --- | ---: | ---: | ---: | ---: |
| Sales Pivot | 161.398 s | 0.468 s | 146.771 s | 2.473 s |
| Invoice Fraud | 68.034 s | 0.564 s | 54.054 s | 1.512 s |
| Excel-in-PowerPoint | 74.309 s | 0.574 s | 54.076 s | 3.071 s |
| Spring Boot migration | 123.804 s | 0.555 s | 78.159 s | 14.003 s |
| React performance debugging | 270.842 s | 0.445 s | 122.865 s | 36.718 s |
| Prefix Cache replay | 61.574 s | 0.408 s | 40.221 s | 2.354 s |

The [pretrial attribution](skillsbench-pretrial-attribution.json) reopens 48
settled operations and completed execution journals across the six runs.
Each run has one protected grader reference and seven probes before the
agent trial. These operations account for 109.607 of the 110.814 seconds
outside React's agent and task grading intervals. The two longest probes
each took about 46 seconds. Their contained executor receipts report 90.856
seconds combined and contain only start and completion events. The remaining
1.207 seconds in the canonical span lack finer attribution. All six runs
have less than 1.4 seconds unassigned after this reconciliation.

The [read-only audit](audit_skillsbench_pretrial.py) produced byte-identical
reports on two passes. Five local controls rejected overlapping, unsettled
and cross-plan charges, a changed receipt, and over-attribution.

For serial private beta work on these pinned configurations, start with a
five-minute review window for document/data and seven minutes for software.
These planning estimates add 50% to the longest measured command in each
domain and round up to a minute. Existing authorized ceilings still apply.
Keep the earlier Sales timeout in its original study. Memory, energy,
concurrency and provider cash remain unmeasured. Resource acceptance stays
open independently of comparison and release.

[Audit driver](audit_assembled_runtime_footprint.py) ·
[Six-task audit driver](audit_skillsbench_resources.py) ·
[Docker measurement definitions](https://docs.docker.com/reference/cli/docker/system/df/)

The full source run with the checkout on `PYTHONPATH` passed 2,165
tests with 21 skips and 81% combined coverage. Both 90% branch gates
passed. The earlier run retained one failure from a subprocess that
imported the installed package. The corrected focused check also passed.

## Evaluator head-to-head

The [ledger audit](evaluator-head-to-head.json) reopens three settled runs
of Markdownify issue 200. Agent-skill-eval 0.7.0 and the managed engine
share the task, actual model, worker, prompt, candidate, advertised
inventory and protected grader. Their saved environment definitions
differ only by ID. The recipe and case IDs preserve the original
label adaptations. The older ordinary Codex control uses the same task
inputs and protected validator with a different prompt, worker and inventory.

| Retained run | Protected score | Reported input + output tokens | Agent seconds | Grading seconds |
| --- | --- | --- | --- | --- |
| agent-skill-eval with controlled Codex | 1/1 | 130,353 | 49.341 | 2.091 |
| Managed engine with controlled Codex | 1/1 | 192,179 | 63.996 | 2.037 |
| Earlier ordinary Codex control | 1/1 | 140,796 | 38.207 | 2.088 |

The agent-skill-eval scheduler has 2.126 seconds of separate exclusive
overhead in the ledger. Each row retains its provider token categories.
Cached input and reasoning sit within their respective reported totals.
Provider cash is unavailable. The ordinary control's report snapshot
predates the end of its outer proxy operation. The audit found that
operation settled under the same reservation and retained the original
report. The parent interval covers the entire original campaign.

The two matched engine runs provide a one-task engineering comparison.
The older ordinary control remains descriptive. The whole repository
family remains excluded from formal stages. Candidate and policy benefits
still require independent controlled evidence.

## Formal candidate and selection gates

The [curated lineage verification](curated-cohort-lineage-verification.json)
covers the service change that lets two curated definitions carry separate
case sets under the same reviewed grader and environment. Each stage still
needs 8/28/105 cases. The qualification and marginal plans need at least
210 distinct holdouts and 36 early-stage cases between them if every early
case can be shared. That puts the optimistic pool of 116 software cases at
least 130 short of the two-stage minimum before source grouping and protected
grading. A native-catalog stage, if run, needs another distinct holdout.
The existing ExtractBench integration definition allows at most six
engineering tasks. The [formal native recipe verification](formal-document-native-verification.json)
adds a separate versioned definition with 8/28/105 reviewed cases. The
document descriptor keeps archive and instruction bytes outside the
assessment definition. The ordinary benchmark CLI staged all three
retained CFPB cases and reproduced their archive and instruction hashes.
The full cohort and protected score handling were exercised with local
fixtures. Native calibration and final cohort adoption remain pending.

The [trial reservation projection](formal-reservation-capacity.json) reads
the current grant with both historical pending reservations still charged.
The snapshot had 2,172 turns and 475,529 seconds available. With the
retained 300-second deadline and one fresh-worker condition, one 8/28/105
qualification plus four-arm value cohort projects 705 trial turns and
257,325 reserved trial seconds. Two separate cohorts would reserve 514,650
trial seconds, 39,121 above the snapshot balance. Adding the catalog
stage for each would also exceed the turn balance by 366.

These projections use one candidate per cohort and the required higher-
compute deadline at twice the ordinary deadline. The frozen dispatch plan
still needs independent cases, measured deadlines and the canonical budget
preview for setup, graders and reporting. Preserve all former charges and
select a finite amendment only when that exact plan needs one.
[Audit command](audit_formal_reservation_capacity.py)

The [formal-input audit](formal-input-audit.json) verified 135 exact retained
asset bindings across 41 provisional Python repository cases from 20
repositories. The audited rows contain 18 single-file repairs, 15 multi-file
repairs and eight contract audits. The audited development-exposure overlay
excludes 24 repository families. Two of those, Canopen and Xsdata, were already
excluded by the October study. Stage assignment remains unfrozen and zero cases
are adopted. Even if all 41 survive final review, the 8/28/105 plan needs at
least 100 additional distinct cases.

The [original transport intake](formal-transport-intake.json) found 39 of
the 41 provisional cases used gzip patches. The
[transport preparation](formal-transport-preparation.json) converted the two
legacy references and fault artifacts to the existing gzip profile. Both
cases sent identical protected archives and wheel inputs through the
coordinator callback. The new profile also checks source module identity.
Synthetic callback responses verified both fault branches and bad-base
rejection. Both cases need protected runtime validation on the new
bindings. The common profile now covers 41 provisional rows, with a
minimum shortfall of 100 before independence and adoption.

The [retained grader audit](retained-grader-evidence.json) reconstructed
the current callback payloads and verified 120 settled historical
observations for 39 of these 41 prospective cases. Each reference passed
and all 39 current fault artifacts map to observed protected rejections.
The audit matched the exact action digests, terminal journals, cleanup
evidence and original image references in the read-only ledgers.
Dissect.cstruct 120 and Mockito 93 still need contained verification on
their current payloads. The audit records the original runtime for
each observation. A shared current runtime and formal cohort assignment
still need verification.
[Reconciliation script](reconcile_repository_grader_evidence.py)

The [grader runtime map](grader-evidence-runtime-map.json) reproduced all
120 settled observations from the read-only ledger against the current
callback. Only the callback source hash changed in the audit output. The
protected grader operations took a median of 2.01 seconds and a
95th-percentile time of 2.93 seconds. These times cover historical
grader operations only.

The retained ARM64 image `35dc1bcb` contains all nine historical image
layer sequences. One of the 39 cases ran on that exact image. Use it as
the candidate for shared-runtime import and protected grading checks.
All historical receipts retain their original image, environment and
observer bindings. The four independently verified Pyserde grades use
an image outside this lineage and a case outside the 41-case pool.

The [exact migration review `864880c7`](migrated-grader-operation-review.json)
binds those four checks to the retained Linux ARM64 image and the ordinary
native pytest observer. The two references and two faults retain their
original archive and wheel hashes. Each has all required outcomes in the
historical reply. The current payload adds the source-module import guard
and an empty explicit plugin list. A third case is an inert recipe fixture
for selecting the native observer. Only the two migrated cases can dispatch.

The [driver](check_migrated_graders.py) passed local checks for success,
missing approval, scope drift, an altered grade, uncertain cleanup and
terminal replay refusal. The router wrote and reconciled real journal and
accounting records on a disposable fixture ledger, with the container
replies substituted. The four actual calls remain unstarted. The review
caps them at four operations and 140 reserved seconds on the existing
grant, with no models, cash, downloads, builds or disclosure. A failed or
uncertain call stops dispatch and leaves settled records available for
recovery.

The cached queue contains 63 potential inputs with matching source archive
hashes and prior license records, 57 without complete matched records and 12
carrying prior exact-source exclusions. The 63 still require task-specific asset
rights, scope, dependency review and independent protected reproduction before
they count. Even if all qualify, at least 37 additional rows need clearance.
Do not treat repository counts or archive integrity as case independence or
qualifying evidence. This audit covers the Python repository cohort. The
document/data workflows have accepted integration evidence and still need
their own independent usefulness workload.

The [repository patch batch](repository-patch-batch-intake.json) applied
published test overlays and repairs to all 63 source-bound leads as inert
data. It staged 42 pairs of source and protected test archives, a published
repair and exact required identities for each. The 42 cases span 29
repositories, with nine multi-file and 33 single-file repairs. All 168
staged files matched in two preparations. The other 21 cases exceeded this
existing-file or protected-test scope. Run compatible subsets under protected
grading after binding their runtime and dependencies. For example, the
SQLACodegen dialect cases still require PostgreSQL or MySQL. The earlier
SQLite check cannot validate those assertions.

The [first offline A2A review](a2a-runtime-intake.json) binds seven published
mocked transport tests to the retained Linux ARM64 carrier. It stages 24
wheels and preserves one Python process with the explicit asyncio plugin.
The original-source control must preserve five passing tests and fail the
two missing context manager checks. Wrong identities, skips and unrelated
errors fail validation. Synthetic driver checks exercised success, failure
and uncertain cleanup. Standalone review `9a31c7ac` remains unstarted.
The grouped review below includes that pair once.

The [worker transport preparation](repository-worker-transport.json) maps
all 42 staged leads through the existing `repository_archive:2` adapter.
The ordinary input root contains only hash-named source archives. The 126
protected files stay in a separate root, and all 42 attempted overlay lookups
through the public mapping failed. No runtime or formal stage was assigned.
If every staged case qualifies, the software pool would contain 83 rows and
would still need at least 58 more. The balanced holdout needs at least 27
additional contract audits and 11 multi-file repairs under that optimistic
count. Stage independence can increase the shortfall.

The [cached-source recovery](cached-repository-rebinding.json) reconstructed
the published Git tree for six cached archives and verified their root
license notice bytes. Four passed the existing inert repair and test-scope
checks. The other 51 caches ended at an earlier download cap. Fourteen of
those have metadata for multi-file changes within the current patch contract,
pending full source verification. The [expanded worker mapping](rebound-worker-transport.json)
now covers 46 staged prospects. All 46 attempts to address private test
overlays through the public mapping failed. The earlier 42 bindings are
unchanged. Excluding A2A issue 472
leaves 86 provisional rows across 52 repository families. Even if all qualify,
the software pool needs at least 55 more rows, including 27 contract audits
and 11 multi-file repairs for the holdout. Repository-disjoint assignment can
increase the shortfall. Three document/data candidates now have protected
reference evidence. They still need asset-use review and ordinary recipe
bindings before stage assignment.
[Updated corpus audit](post-protected-corpus-status.json)

The [archive recovery](multifile-acquisition-result.json) verified four of
13 exact public sources. Three passed existing multi-file scope checks and
ordinary worker transport. One archive has a symlink and the worker contract
rejected it. The acquisition driver initially omitted the pinned issue
metadata beside each archive. Local staging paired the original metadata
with the verified bytes and recovered the three bindings without further
downloads. The optimistic software pool now has 89 rows. At least 52 more
are required, including 27 contract audits and eight multi-file repairs for
the holdout. The three recovered candidates still need protected runtime
verification and source-disjoint assignment.

The [additional contract audits](additional-contract-audits.json) use
five distinct retained revisions from Venvstacks, Build, Twine, tox and
Towncrier. The public inputs carry the published Python repair. The empty
reference and original-source fault stay beside the protected tests.
All 183 published test identities remain. The only omitted edits are
the recorded changelog and documentation changes. The five preservation
guards accepted the repaired bytes and rejected seven one-file restorations.
Separate preparations produced identical bytes. All cases still need
protected runtime verification. The optimistic pool now has 94 rows
across 60 repository families, leaving at least 47 missing before formal
stage assignment. The 105-case holdout still lacks at least 22 audits
and eight multi-file repairs.

Three [cached multi-file projections](cached-multifile-projections.json)
recover the retained Sentry, PDFly and Hugging Face Hub candidates. The
Sentry and PDFly archives match their published trees when the exact
submodule pointers are included in the identity check. Their contents
stay outside the worker archive. Hugging Face Hub's complete archived
tree matched, and the worker projection excludes its upstream instruction
file and symlink. All three preserve the 66 published test identities.
A fresh inert preparation reproduced every byte. The controls rejected
incorrect submodule pointers and an unexpected symlink.
The PDFly verifier needs the pinned submodule's three-page PDF. The private
copy matched the published Git blob. The publisher's notices identify it
as CC BY-SA 4.0. The verifier still needs the file at its original relative
path inside the protected grader. Sentry's optional schema and the other
runtime dependencies need protected verification. The optimistic software
pool now has 97 rows. The shortfall is at least 44, including 22 contract
audits and five multi-file repairs for the holdout.
[Publisher fixture notice](https://raw.githubusercontent.com/py-pdf/sample-files/91b6d24a3b86bad1f20b707ec54555d89acc0c12/README.md)

The [PDFly placement check](pdfly-protected-fixture-placement.json) stages
the exact PDF and publisher notices under the protected test root. The
first-party bootstrap restores them at their upstream relative paths before
PDFly imports. It rejected a pre-existing destination, corrupted bytes and
a symlink. The reference, original and three one-file-drop payloads all
preserve the single issue test and three preservation tests. Two preparations
matched byte for byte with substituted replies. The public archive stays
fixed.

Five direct dependency artifacts in the retained lock match local wheels.
Seven platform-compatible wheel candidates are missing. The only pinned
Pillow and cryptography wheel entries target x86-64. Review a compatible
dependency closure before genuine protected grading. The partial repairs
have no measured outcomes yet.

Eight [audits with frozen project metadata](ancillary-contract-audits.json)
recover Arta, Raygun4py, Confluence Markdown Exporter, AnyIO, Skelebot,
py-fsrs, pygls and Fromager. The public source uses the exact upstream
Python repair and the reviewed patched metadata. The restored-source
control restores only the published Python changes. Ten metadata files
match in both roles. The py-fsrs CI schedule change stays outside the
test overlay, with all published test identities retained. Inert
preparation preserved 596 identities and rejected 18 single-file
restorations through local preservation guards. Separate preparations
matched byte for byte. Grader runtime and upstream reference and fault
results remain open. The optimistic software pool has 105 of 141 rows,
with at least 14 contract audits and five multi-file repairs still
needed for the holdout.

The [native pair runtime preflight](cached-native-pair-preflight.json)
binds Sentry and Hugging Face Hub to the retained Linux ARM64 grader,
exact cached wheels and the ordinary native pytest callback. It rebuilt
all four protected payloads. The Sentry profile supplies pytest-cov and
uses the carrier's jsonschema. The Hugging Face Hub profile supplies
pytest-mock. The selected tqdm module still needs real collection to
verify the retained profile suffices with HF-Xet absent.
Six substituted driver checks verified approval and drift refusal,
settlement, independent progress after a missing identity and an
unresolved reservation after uncertain cleanup. Exact review `72354f5a`
permits four offline calls and 140 reserved seconds at zero models and
$0. The review is unstarted and pending authorization.

The [repository expansion preflight](repository-expansion-preflight.json)
reads all nine retained pages of the pinned SWE-rebench union. The
local screen excludes previously used or considered repositories,
unreviewed patch shapes and missing test identities. It retained 283
leads across 159 repository families. The pinned replay matched both
private queue files byte for byte. The public repository metadata
check issued 60 requests and verified 53 entries. Current repository
size and license fields inform source prioritization. The acquisition
driver verifies the exact archived Git tree and root license notice
before any case advances.

The [private acquisition review](repository-expansion-preflight.json)
binds 48 exact source revisions. It tests whether 31 separate audit
origins and 17 multi-file repairs can move through the existing
protected staging path. The cap is 168 MB of archive responses and
9.22 MB of commit metadata. Six first-party driver checks exercised
both roles with retained bytes, approval and drift refusal, a transport
failure and a publisher rate limit. The batch is unstarted. A
successful archive binding still needs runtime reproduction, rights
review and source-disjoint stage assignment before formal use.

The [source-disjoint capacity audit](repository-capacity-audit.json)
checks the proposed corpus against the 8/28/105 plan. The current 105
prospects include 54 single-file repairs, 30 multi-file repairs and 21
contract audits. The headcount gap is 36. Balancing the three workload
families in each stage needs at least 42 new sources. Either 25 audits
and 17 multi-file repairs or 26 audits and 16 multi-file repairs can
fill the plan if every retained prospect qualifies. Both projections
keep each repository in one stage and put 35 cases of each family in
holdout. With two multi-file failures, the 48-source review alone
cannot fill the plan. Twenty-five distinct multi-file leads remain
outside the review. The audit replay matched byte for byte. No case
was assigned, downloaded or run.

The [current carrier projection](formal-reservation-capacity.json)
excludes all three Fabric CI/CD cases that declare Python below 3.13.
Two are multi-file repairs. That leaves 28 staged multi-file prospects.
The pending batch adds at most 17, and the balanced schedule needs
at least 46 across the three stages. With the current carrier, add
at least one multi-file case or verify an applicable runtime for one
of the excluded multi-file sources. Actual protected acceptance and
stage assignment remain open.

The [pyserde repair intake](pyserde-production-repair-preflight.json)
matches a distinct retained archive to its published Git tree and keeps
both production diffs and all five tests from PR 682. The repair scope
omits the example program and its example runner change. The ordinary
callback staged the reference, original and both one-file repairs using
substituted responses. Protected grading still needs to establish which
outputs pass and whether both edits are independently necessary.

The [ordinary grader result](pyserde-ordinary-result.json) verifies the
published repair on the retained Linux ARM64 image with all 12 locked
dependencies. The 173-file agent archive excludes the new issue assertion.
The two production files are its only editable paths. The reference passed
5/5. The original and both one-file partials passed four preservation tests
and failed the same issue test.
All five operations settled in 7.539 summed seconds, with zero model turns
and $0 cash. Both Pyserde revisions must stay in one stage. The source-disjoint
projection still requires 26 audits and all 17 multi-file repairs from the
pending acquisition batch and their protected acceptance.
[Publisher PR](https://github.com/yukinarit/pyserde/pull/682) ·
[Staging driver](stage_pyserde_production_repair.py)

The [staged grader audit](staged-repository-grader-bindings.json) exercised
the ordinary callback on 64 additional source-bound cases with substituted
pytest replies. Both archive roles for every case stayed within the transport
limit with the pinned base pytest stack and retain 8,338 test identities.
All three Fabric CI/CD cases declare Python below 3.13. Universal Pathlib
529 needs a separate collection preflight. Its S3 tests inherit assertions
from shared test classes and use a local S3 server fixture. The existing
A2A receipts retain their original scope. Per-case runtime closure,
actual grading and formal assignment remain open.
The 117 focused grader and benchmark tests, schema check, and offline
documentation check passed. The audit reproduced its result byte for byte.
[Audit driver](audit_staged_repository_graders.py)

The [first staged protected batch](staged-protected-pair-preflight.json)
covers a py-fsrs contract audit, a files-to-prompt repair and a py3status
repair. The three cases retain 54 required test identities. The existing
Linux ARM64 image supplies setuptools 75.8.2. Its wheel exceeds the
ordinary per-file transport bound. Files-to-prompt uses an exact cached
Click wheel. Both asset roles retain their original archive hashes.

The [driver](check_staged_offline_cases.py) rehearsed all six calls through
the actual ledger and attempt journal with substitute container replies.
It also verified missing-test, unauthorized, changed-review and unknown
cleanup paths. A settled reference mismatch skips only its counterexample.
Exact review `f818cc19` allows up to six offline operations and 210
reserved seconds at zero model turns and $0. Upstream runs remain
unstarted. The review reproduced byte for byte. All 128 focused tests,
schema checks and offline documentation checks passed. No formal cases
are assigned.

The [Wemake selector preflight](wemake-native-selector-preflight.json)
reconstructed all 117 projected test identities from the literal upstream
parameters. The 27 published selectors include 19 prefixes. Their synthetic
expansion preserves 36 issue checks and 81 preservation checks. The protected
runtime still needs the pinned Python and Flake8 dependencies and must collect
the same identities before any result enters the corpus.

The [independent document pack](independent-document-pack-intake.json)
binds 26 original files to the pinned SkillsBench Git tree. Ordinary CLI
inspection passed for workbook recovery, Formula Extraction and economic
detrending. The staged archives contain exactly two, two and four files,
respectively. Each contains its instruction and original inputs. Protected
tests, reference data, build inputs and bundled skills stay outside the
archives. The pack is local and prospective.

The [grouped A2A review](a2a-batch-intake.json) covers three published
source revisions and 127 required test identities. Each reference must
pass every required test. Each original must fail its issue assertions and
pass its preservation assertions. The 25-wheel closure uses the retained
Linux ARM64 carrier. Each call mounts only the shared runtime and its own
read-only source and protected test fixture. Six driver checks exercised
approval and drift refusal, successful settlement, a settled failure and
uncertain cleanup with synthetic executor replies.

Approved review `e7f6f735` ran in place of the standalone `9a31c7ac`.
Issues 576 and 682 reproduced both reference and original-source results.
Issue 472 stopped at collection before its original-source control. The
published selector adds `Task` to the only matching function name. The
same test body is present in both fixtures. The batch settled five calls
in 12.94 seconds with zero models and $0. The three snapshots share one
repository family, and none has a formal stage assignment.
[Protected receipts and diagnosis](approved-a2a-batch-results.json)

The approved selector correction ran all 81 identities on both fixtures
for issue 472. The reference passed all 81. The original passed 78 and
failed three, one fewer failure than the published contract requires.
The fourth test, `test_on_cancel_task_queue_tap_returns_none`, passed on
both fixtures. The selected test and cancellation-handler function bytes
match across the two pinned fixtures. Keep issue 472 out of the formal
pool at this pin. The two successful pairs were preserved without replay.
[Settled protected results](protected-reference-group-result.json)

The [A2A receipt bridge audit](a2a-receipt-bridge-audit.json) matched four
retained receipts to settled ledger entries. The ordinary grading callback
rebuilt the same protected archives. It scored both published repairs 1/1 and
both original snapshots 0/1 from the recorded test outcomes. Missing
assertions, a mismatched archive and an incorrect patch base were rejected.
This read-only check ran no upstream tests. A common contained runtime still
needs the existing compiled dependencies, the larger Pygments wheel and a
verified selector scope. Issue 682 also needs the reviewed pytest override.
No case entered a formal stage.
The audit reproduced byte for byte. All 156 targeted repository tests,
schema drift verification and the 72-file offline documentation check passed.

The [ordinary runtime preparation](a2a-ordinary-preparation.json)
stages the same 1,179 dependency files in a private COPY-only overlay. The
ordinary observer uses its existing native pytest capture with the reviewed
options from the direct check. The case definitions rebuilt all four
protected archives without extra host mounts. Three authored launcher checks
and five copied-ledger driver scenarios passed. Uncertain cleanup kept the
current reservation open and stopped further dispatch. Review `56ed2748`
covers one local build and four protected calls, capped at 265 additional
reserved seconds, zero models and $0. The build and module-wide verification
are unstarted. Both snapshots remain provisional.

The next [workload intake](workload-intake-audit.json) checks both domains.
On the software side, two original patches and protected test overlays apply
cleanly. One of the two has a retained collection failure. The other needs
its exact runtime closure and protected execution before adoption. On the
document/data side, eight additional SkillsBench entries have metadata pinned
to the same revision as the six integration tasks.

The [document corpus metadata audit](document-corpus-metadata.json) pins
two upstream workload sources for the independent document/data study.
It reads 926,087 bytes of official metadata and verifier text. The
ExtractBench manifest and file listing agree on 370 tasks and 370 unique
PDF digests. The tasks use 71 distinct schema digests. The largest schema
group has 18 tasks. Whole-source provenance still needs review across
files with different hashes. The 20 long cases fall short of the 35
needed for a holdout balanced by length. The three sample declarations
validate against the existing task asset contract and separate the
document and schema from the reference answers and grader.

The [source-group audit](extractbench-source-group-capacity.json) ties 38
named clean/degraded pairs together. Three also have different answer hashes.
It collapses page excerpts and matching answer hashes and keeps schema-linked
families within one stage. Excluding the six Audent development-family cases
leaves 294 metadata slots across 69 families. An illustrative packing fits
two 8/28/105 cohorts with 12 spare slots. Only 17 long slots remain across
the whole pool. Each illustrative holdout has two long documents. This is
a capacity check pending source and rights review, protected grading and
formal assignment.

The [document cohort intake](extractbench-cohort-intake-witness.json)
also reserves the CFPB family for scorer checks. From 291 metadata slots,
two fully separate 8/28/105 layouts each hold out six long, 40 medium and
59 short entries. They leave nine slots unused. Losing any one of nine
larger families would make the fully separate count unattainable from these
records. A shared-early layout holds out seven long, 41 medium and 57 short
entries per cohort and leaves 45 slots unused. Both layouts reproduced
byte for byte. Their metadata keeps related cases in one stage and excludes
the known development family.

Matching length mixes across cohorts leave the formal variation rule
open. If length defines the three formal variations, two balanced
holdouts need 70 long entries. Only 17 long metadata slots remain before
the early-stage counts. Permitted use, exact inputs and actual protected
grading still need evidence. Keep the illustrative layouts outside the
operational ledger.

The [CFPB case review](extractbench-cfpb-source-review.json) verifies nine
input files across three tasks against the upstream manifest and matches their
PDFs to CFPB originals. Both refinance examples match all pages. The
benchmark's filled example matches the five form pages of the fixed-rate
sample. The comparison covers text and rendered pixels. The three degraded
copies share the same source family. All oracle files stay outside the
verified input roots. The task declarations still need protected grading
and approval for provider disclosure.
[CFPB model forms](https://www.consumerfinance.gov/rules-policy/regulations/1026/2026-04-08/h/) ·
[CFPB source-use notice](https://www.consumerfinance.gov/privacy/website-privacy-policy/)

The [CFPB protected preparation](extractbench-cfpb-protected-preparation.json)
checks the publisher solutions against the grader references and the
reference schemas against the inputs. It reuses the pinned scorer in three
case-bound protected roots. Each has seven roles covering the reference,
missing and duplicated rows, a changed value, malformed and missing output,
and an unavailable reference. The observer commands passed the ordinary
container boundary checks offline. Run the existing native calibration
before reviewing these three protected calls.

The original ExtractBench Harbor verifier uses value F1 and reports
perfect-document status separately. Its Dockerfile fetches a scorer and
dependencies at build time. Exact offline dependency review, grader
controls and asset-use records must precede any execution. The ordinary
SkillsBench workflow remains the integration path.
[ExtractBench dataset](https://huggingface.co/datasets/llamaindex/ExtractBench/tree/f9b910906cd7e73cc9eb5379a8d5d935c67b92c4)

The [13F development intake](extractbench-audent-intake.json) verifies all
11 files for one ExtractBench task. The two-page PDF and the protected
reference agree with the SEC table on all 52 security identifiers,
values and share counts. Exactly three files are staged as agent inputs.
The reference, solver and verifier stay private. The calibration keeps
native value F1 and the perfect-document indicator. It stages the original
reference, a missing row, a changed value, a repeated row and malformed
JSON. Treat the six tasks that share this schema as a development family.
[Official SEC filing](https://www.sec.gov/Archives/edgar/data/1834874/000208585326000296/0002085853-26-000296-index.htm) ·
[SEC reuse guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions)

The publisher's pinned base lock has 70 compatible CPython 3.13 Linux
ARM64 wheels and no matching wheel for `fuzzysearch==0.8.1`. Thirty-two
of the 70 wheels match existing caches byte for byte. The other 38 total
77.73 MB. Resolve the offline scorer's import closure before choosing
which artifacts to acquire. Native scoring and disclosure authority
remain open. [Read-only calibration audit](audit_extractbench_audent.py)

The [runtime audit](extractbench-runtime-audit.json) follows the original
verifier and 89 imported modules, including the ExtractBench and ParseBench
package initializers. NumPy and SciPy provide the native array matching
and scoring, with 48.56 MB of combined wheels. Three registries attempt
another 79 imports at startup. Keep the publisher's base lock projection
for the offline check until a smaller closure is verified. Of its 70
wheels, 34 are now cached and 36 still need acquisition (76.70 MB).

The verified fuzzysearch 0.8.1 source archive includes the publisher's
Python fallback for its compiled extensions. Its compatibility and the
native value-F1 controls still need a contained run. No grader ran and
no case was admitted. [Runtime audit command](audit_extractbench_runtime.py) ·
[Publisher scorer](https://github.com/run-llama/ExtractBench/tree/2f27f100730afc7c395602e26a2a87e07ea66b31) ·
[fuzzysearch release](https://pypi.org/project/fuzzysearch/0.8.1/)

The [protected intake](extractbench-protected-runtime-intake.json) matched
all 379 archived blobs to the pinned Git tree. It stages 282 package
files, the original verifier and protected calibration assets in a
separate grader mount. The verifier has one reversible document-path
adaptation. The native loader, metric and oracle remain unchanged.

The [observer](extractbench_harbor_observer.py) preserves fractional
value F1, a separate perfect indicator and upstream feedback counts.
It keeps infrastructure errors ungraded and excludes cell contents
from its summary. Seven substituted roles passed, including malformed
and absent output and an absent reference. All 12 source, path and
observer checks passed. Acquisition of the 36 remaining pinned wheels
and offline verification with the actual scorer remain open.
[Staging command](stage_extractbench_protected_inputs.py)

The [execution review](extractbench-native-grade-preflight.json) binds
the entire locked wheel set, the protected mount and the retained Linux
ARM64 carrier. It allows 36 exact downloads totaling 76,701,027 bytes
and one offline container. The guest checks all 70 installed wheel
versions, then loads the verified fuzzysearch source fallback and runs
the seven protected cases. Installation stays in temporary guest storage.
The [driver](check_extractbench_native_grade.py) caps the two operations
at 755 reserved seconds with zero model turns and $0. The rehearsal
verified the installer arguments, score guards, and accounting for
success, missing approval, acquisition failure and uncertain cleanup.
Exact review `ba9f3388` retained seven new wheels and stopped before
the grader launched. The metadata reader counted a vendored HTML5lib
record inside the Bleach wheel as a second distribution. The original
operation settled in 0.330 seconds. The [continuation preflight](extractbench-native-grade-continuation-preflight.json)
verifies all 41 retained wheels and records the 29 unstarted URLs,
74,481,611 exact bytes and one protected offline grader call. The
[corrected driver](continue_extractbench_native_grade.py) passed six
wheel rejection checks, four substituted accounting scenarios and an
exact-review drift check. Review `8e1713c5` needs authorization.

[Repository source intake `bb4a134f`](repository-expansion-acquisition-result.json)
finished all 48 attempts. It verified Git tree and license bindings for
11 authored audits and two multi-file repairs. All 26 substituted callback
checks passed. The other 35 attempts remain outside the pool. Twenty-nine
lack a retained archive, and the old driver preserves only their failure
class. Four retained archives are readable without a verified publisher
match. Two passed the Git inventory and then failed transport staging.
AiiDA's archive contains 15 non-regular entries under its tests. Removing
the root `AGENTS.md` from an inert OpenAI Agents projection preserved both
edit paths and all 24 identities. No upstream tests ran in the intake or
the follow-up audit.

If every current software prospect qualifies, the 116 possible cases
still fall at least 25 short of the 141 required. The stated balanced
8/28/105 profile still needs 15 audits and 15 multi-file repairs. Retain
the prior source groups and protected grader requirements.

SpreadsheetBench 2's revised paper reports 297 cell-graded tasks and
24 visualization tasks. The publisher's archive history lists a June
upload and a separately named September upload. Both hashes are pinned
in the metadata audit. The link between those hashes and the paper's counts
remains unverified. The dataset card declares MIT. The revised paper
declares CC BY-SA 4.0 for the released dataset and MIT for the evaluator.
Archive selection and permitted use remain open.
[Dataset card](https://huggingface.co/datasets/KAKA22/SpreadsheetBench-v2) ·
[Archive history](https://huggingface.co/datasets/KAKA22/SpreadsheetBench-v2/commits/main) ·
[Revised paper license statement](https://arxiv.org/html/2606.29955v2#A4)

The paper describes full-workbook accuracy. The pinned cell evaluator
iterates the task's declared answer ranges. Check which cells those ranges
cover on each selected workbook before making a preservation claim. The
documented evaluation requires recalculation, and visualization uses a
separate model. Both archives await acquisition.
[Paper evaluation metrics](https://arxiv.org/html/2606.29955v2#S2.SS4) ·
[Pinned evaluator](https://github.com/RUCKBReasoning/SpreadsheetBench-2/blob/a7bdc2d358e052d35a94768e1f487c0d9e9c0011/evaluation/evaluation.py)

The [audit script](audit_document_corpus_capacity.py) reproduced the
report from 14 retained documents and rejected five altered source
bindings. No task assets were acquired and no formal split was assigned.

The [document verifier screening](document-verifier-screening.json) read
12 pinned source files and reviewed 35 test functions across four more
SkillsBench tasks. Keep the PDF, presentation, and both Georgia investment
shock tasks out of formal trials at these pins. The checked assertions can
miss misplaced form text, an unreachable reference slide, missing demand
scenarios or an unfitted supply trend. These are static findings. No verifier
ran and no case qualified.

For the [economic detrending case](economic-case-review.json), the two
bundled ERP tables match the official downloads byte for byte. All 52 CPI
entries reproduce from annual means of the unadjusted BLS series divided
by its 2024 mean. The supplied task links the seasonally adjusted series.
An independent calculation matched the reference to five decimals. The
original tolerance would also accept a calculation missing 2024, even
though the answer changes at the requested precision. Keep the case
provisional until a supplemental control and a protected runtime check
are frozen and verified. No verifier, agent or candidate ran.
[GovInfo tables](https://www.govinfo.gov/app/collection/erp/2025) ·
[BLS series via FRED](https://fred.stlouisfed.org/series/CPIAUCNS)

The [economic protected reference](economic-protected-reference-preparation.json)
now binds the unchanged four tests and a separate exact five-decimal check.
Approved review `e0b675f2` ran the five artifacts offline. The reference
scored 1/1 using both checks. The upstream tests accepted the omitted 2024
data and excess precision; the supplemental check rejected both. The
combined grader also rejected wrong smoothing and missing output.
This verifies the proposed supplemental grader. Formal adoption and
provider disclosure remain open.

The [ordinary recipe](economic-ordinary-recipe-preparation.json) binds the
same verified tests and independent answer to the existing contained
command and case format. The approved run passed the reference command.
The grader stopped at startup because the embedded observer expected
`__file__` in a `python -c` command. Both operations settled and the
owned containers were removed. The [corrected continuation](economic-ordinary-continuation-review.json)
reuses the reference and keeps both charges on the original ledger. It
awaits exact repeat approval. [Initial result](economic-ordinary-initial-result.json)

The [workbook preservation preflight](workbook-preservation-preflight.json)
extracted 15 marked gaps from the four original sheets. Its supplemental
check preserves populated cells outside those gaps and requires finite
numeric replacements. One synthetic replacement control passed. Eight
controls, including a changed title and an added cell, were rejected.
The protected upstream verifier has its own retained evidence below.

The [ordinary workbook recipe](workbook-ordinary-preparation.json) stages a
COPY-only context with 16 pinned files and the original verifier and solver.
The zero-value control changes precisely the 15 marked gaps. The other
control alters one populated title. The [operation review](workbook-ordinary-operation-review.json)
binds the build, reference and grade commands and preserves both earlier
accounting histories. The copied-ledger preflight exercised success,
scope drift, failed build, failed grade and uncertain cleanup. The exact
protected repeat awaits operator approval.

The first new document/data reference, `xlsx-recover-data`, passed all 19
upstream checks. Missing output produced one failure and 18 skips. The
unchanged workbook produced one pass and 18 failures. A bootstrap attempt
failed before loading the upstream code because the selected image used
`python3` at a different path. The corrected launch used the Python command
from the established grader on the same image. All four operations settled,
including the bootstrap failure. The task has never been sent to an agent.
[Protected workbook result](workbook-reference-result.json)

The existing task-pack transport verified a two-file workbook archive with
only the original task instruction and incomplete input. Linux ARM64
installed the same 33 package versions as macOS using six platform-specific
wheel variants. On glibc 2.41 and Python 3.13.15, repeat installation
preserved the journal, and candidate inspection retained the same identity.
Both reports matched the macOS fixture byte for byte. Removal preserved
the neighboring file and the staged candidate, and the owned container
was removed. This result covers the pinned Linux ARM64 container and package
closure. The separate [clean macOS rollback](macos-private-rollback-result.json)
passed on the reviewed native runtime.
[Transport and compatibility preflight](transport-and-compatibility-preflight.json)
[Linux install and removal result](linux-private-install-result.json)

The first Linux launch rejected 40 stale dependency-manifest references before
installation. The corrected graph passed preview for all 33 packages. That
launch then stopped while importing the installer. The read-only inventory
found no `packaging` module in any of the carrier's seven layers. The proposed
approved repeat adds the same pinned `packaging` wheel from the audited
closure to the bootstrap import path. Review `c3a6be5b` passed in 10.11 seconds.
All three owned containers were removed. The first launch retains its 270-second
reservation because the launcher could not construct the measurement receipt.
The corrected bootstrap settled at 1.19 seconds. Both bootstrap failures
stopped before package installation. All three operations used zero models
and zero cash.
[First bootstrap result](linux-private-install-bootstrap-result.json) ·
[Corrected bootstrap result](linux-private-install-bootstrap-correction-result.json) ·
[Carrier inventory](linux-carrier-inventory.json)

The FuseSoC reference has 17 verified runtime wheels and a notice from the
wheel or pinned source archive for each dependency. The fixture binds 246
original source files, a separate protected test overlay and the original
three-file repair. The 15 published test identities stay fixed. MarkupSafe
and PyYAML use platform wheels, so a protected runtime must supply those
exact artifacts separately from the portable-wheel probe payload. The case
remains provisional. The first protected run collected all 15 published tests
and all 15 failed on the reference, so the original-source control stayed
unstarted. Each test constructs a default configuration that creates a cache.
The first runner leaves that cache on the container's default home path.
The fixture retains only aggregate verdicts, so the immediate exception is
unknown. Review `992e408d` prepares a retry with cache and config inside a
fresh per-trial scratch directory and records bounded exception categories.
The earlier result and charge are preserved.
[FuseSoC runtime preflight](fusesoc-runtime-intake.json) ·
[First protected result](fusesoc-protected-reference-result.json)

The scratch correction `992e408d` matched all 1,161 retained file bindings,
the image layers, the driver and the frozen source. Six first-party driver
checks covered approval and drift guards, settlement, reference failure and
uncertain cleanup. The approved repeat collected all 15 tests. Every test
failed with `ModuleNotFoundError`. The observer retained the exception
category. Static inspection found that `fusesoc.lockfile` imports
`fusesoc.version`, which the upstream build generates through setuptools-scm.
Both staged archives and the support tree lack that module. The original-source
control stayed unstarted. The one operation settled in 3.263 seconds. Keep
the case provisional pending a build-metadata binding at the exact revision.
[Repeat and diagnosis](fusesoc-scratch-correction-result.json) ·
[Pinned upstream build configuration](https://raw.githubusercontent.com/olofk/fusesoc/d2e6e720222f57cb66d6c303a326d336c582aade/pyproject.toml)

The [build-metadata preflight](fusesoc-build-metadata-preflight.json)
pins FuseSoC's snapshot 49 commits after tag 2.4.5. During grading,
setuptools-scm 8.3.1 will generate the missing module in each fresh
protected source tree using the full commit SHA. The existing source,
patch, test archives and all 15 assertions stay unchanged. Six
first-party rehearsals exercised approval refusal, settlement and
error handling. Exact review `18e8cfc1` allows one offline reference
repeat and the previously unstarted original-source control after a
pass. At most two operations and 100 reserved seconds. The review has
no model calls, cash, build or install. Both protected calls are unstarted.
[Upstream version rules](https://setuptools-scm.readthedocs.io/v8.3.1/usage/) ·
[Pinned publication](https://pypi.org/project/setuptools-scm/8.3.1/)

The [static workbook screening](workbook-grader-screening.json) verified 14
assets across three further SkillsBench cases. Protein Expression checks cell
presence and types. Powerlifting's accuracy tests recalculate from the input
sheet without evaluating the submitted formulas. Both can accept incorrect
output. Exclude them at these verifier pins. Weighted GDP checks numeric
results as well as formulas. Its workbook contains an external link, and its
verifier depends on Gnumeric to recalculate formulas. It stays provisional
until source rights, offline recalculation and reference and failure paths
are verified. All three cases stayed local and unexecuted.

The [Formula Extraction intake](formula-extraction-intake.json) verified six
pinned assets and found seven declared checks, including a rendered comparison.
The [verifier review](formula-verifier-assessment.json) matches the exact
three-page input to its first author's contribution to SkillsBench. It also
shows that the pinned Pillow comparison checks only the difference in alpha
by default. A synthetic control with equal alpha and different color passed
the original rule. The proposed all-channel comparison rejected it and
still accepted identical pixels. The immutable upstream verifier remains
available. The contribution and license notice support provenance.
Asset-use approval remains separate.
[Input contribution](https://github.com/benchflow-ai/skillsbench/commit/b0ebf1b3ed9556c21ffcd754a88f1d65e3ef56f6)
[Pillow 10.4.0 comparison](https://raw.githubusercontent.com/python-pillow/Pillow/10.4.0/src/PIL/Image.py)

The [offline renderer preparation](formula-offline-preparation.json) keeps
all seven upstream test bodies intact. The staged inputs cover the exact
oracle, a wrong formula with the same line count, a missing formula and an
unavailable renderer. The infrastructure control must return no task grade.
MathJax 3.2.2 and nine supporting wheels are retained. The old browser is
revision 1148. The pinned Playwright 1.57.0 verifier requires revision 1200.
Its matching Chromium archive was inspected with a 65,557-byte metadata
range. Approved review `bedcde5c` received and verified the two artifacts
at 160,981,322 bytes total. The browser archive has a recorded SHA-256.
Approved review `fa6d72b8` ran the four protected roles against the
corrected pixel comparison. The reference passed all seven checks
and scored 1/1. The same-length wrong formula and incomplete output
scored 0/1. With the local MathJax script withheld, the renderer timed out
and the grader returned an infrastructure error with no task grade. All
four roles ran with networking disabled.
[Acquisition result](formula-runtime-acquisition-result.json)
[Playwright browser pin](https://raw.githubusercontent.com/microsoft/playwright/v1.57.0/packages/playwright-core/browsers.json)
[Chrome publisher metadata](https://googlechromelabs.github.io/chrome-for-testing/143.0.7499.4.json)

The [ordinary Formula Extraction recipe](formula-ordinary-preparation.json)
uses the original task input and checks, with the recorded all-channel pixel
correction. The protected grader accepts only the declared Markdown artifact,
up to 32,768 UTF-8 bytes. A first-party check reproduced the four historical
dispositions, rejected six malformed artifacts and two input or reference
binding changes, and verified the four contained command shapes. The local
COPY-only context has 2,755 pinned files totaling 458,297,419 bytes. No new
protected invocation or image build ran. Exact runtime verification, task
asset rights and provider disclosure remain separate.

The [exact offline review `73cee6d8`](formula-ordinary-operation-review.json)
covers one COPY-only build and four ordinary calls on Linux AMD64. It binds
the local Docker builder, parent layers, sealed context and protected command
templates. The [first-party driver preflight](formula-ordinary-driver-preflight.json)
covers seven cases, including a wrong grade, uncertain cleanup and a final
report write failure after all receipts settled. The build and verifier calls
remain unstarted while the exact repeat approval is pending.

The [grouped review](protected-reference-group.json) covered seven local
operations. The [result](protected-reference-group-result.json) reconciles
all seven receipts and operation entries against the canonical databases
in read-only mode. The settled intervals total 53.644 seconds across the
operations. The group used zero model turns and \$0. No case was adopted.

The selection recorder now rejects a route decision with no feasible executor.
Only an actual baseline choice records abstention. A blocked route leaves the
selection matrix incomplete. No live selection result was added. The 37-check acceptance
still refers to its recorded source. Updated source requires its own binding
before a new live study. An offline Router check confirmed that the blocked
decision is stored with the input redacted and creates no execution receipt.
For the live study, capture the case and decision digests when the route is
made. The redacted decision alone cannot prove what input the policy saw.
The selection report's existing data contract is unchanged.

The [selection capture](capture_selection_route.py) reserves one local
routing operation on the reviewed assessment request. It matches the frozen
action and shared routing pool, records the decision digest before returning
the route, and keeps task contents out of the capture. A read-only consumer
can bind a later receipt to that choice. The capture and Router times stay
available. A blocked route cannot become an abstention. An interrupted
routing operation keeps its reservation and blocks another dispatch.

The [preflight](selection-route-capture-preflight.json) passed seven scenarios
and ten receipt-link checks, including a receipt read from a reopened
read-only ledger. It used the real local Router on synthetic tasks with
network connections denied. The receipt links were tested with synthetic
receipts. The hook did not execute tasks, grade outputs, or invoke models.
Apply it to a reviewed equal-inventory policy study after independent
candidate evidence exists. Guardrails, case counts and policy comparisons
still require their own evidence.

The [selected-trial binding](bind_selection_trial.py) uses the ordinary
BenchmarkRunner hook for a single reviewed case and policy choice. It
freezes the case and grader before selection, then rechecks the selected
executor and shared runner inventory before dispatch. The read-only check
reopens the separate execution decision, exact pinned action, receipt,
terminal journal and protected callback grade. Selection, execution and
grading have distinct settled ledger references. Task contents stay out
of the selection records.

The [first-party preflight](selection-trial-preflight.json) used the real
Router, runner, and grader on the current committed source. The valid
baseline and candidate calls both scored 1/1. A wrong-output control scored
0/1. All nine operations and 27 refusal checks used disposable local
ledgers and zero model turns. The remaining work is connecting the
reviewed discovery-only and fixed policies and obtaining independent
candidate evidence before a live selection study.
[Verification script](verify_selection_trial.py)

The [discovery and fixed controls](selection_controls.py) now use the same
pre-task capture and protected execution path as the AEEP arm. Discovery
calls the existing DiscoveryService on a reviewed local metadata snapshot.
Its query is pinned, and it follows catalog order for exact matches in the
shared inventory. The fixed arm follows a separately reviewed preference
from earlier development evidence. A fixed preference cannot draw on the
current task. The read-only source check reopened one complete historical
assessment and refused changed prior task references.

Both controls share the Router's feasibility checks and disregard its
ranking. Each records the common Router time, the preference time and the
full measured decision interval separately. A control uses the baseline
only if it passes the same constraints. The choice record preserves the
source and never grants dispatch authority.

The [three-policy fixture](selection-controls-preflight.json) produced three
different choices from the same task and inventory. All three settled
protected grades were 1/1, and the existing selection scorer found a matched
grade and decision time for every policy pair. The result remains
NOT_ASSESSED. The historical [single-choice preflight](selection-trial-preflight.json)
keeps its original driver hashes. The live fixed-choice review still needs
independent candidate evidence and frozen comparative workloads.

The [selection measurement check](selection-measurement-verification.json)
uses the original attempt journal and canonical trial to report per-task
scores, decision time, agent time, grading time and Codex token categories.
It leaves a token delta unknown if the corresponding counter or a
compatible capture source is missing. Cached input and reasoning output
remain subsets of the parent counts. The report links each observation to
its protected grade and receipt.

Two local three-policy runs produced identical verification results.
The reader also reproduced all six retained receipt measurements for
Sales Pivot, CANopen and Xsdata. These are historical capability runs.
The new checks used no model turns and added no formal selection evidence.

The ordinary regression run passed 2,181 tests with 21 skips. The
coverage run reported two teardown errors because pytest's fixture
cleanup used the file-open function those tests patched. Both tests
passed under coverage with default retention. The combined coverage
passed both branch gates. The report retains the original failure log.

The committed snapshot passed 42 targeted tests, schema checks and the
wheel build with a stable source fingerprint. Both full workspace runs passed
2,165 tests with 21 skips and 81.45% combined coverage. Both branch gates
passed. Finder changed the workspace fingerprint during verification, so the
full runs retain their workspace scope.
[Selection verification](selection-guard-verification.json)
[Selection guide](../../../../docs/aeep-toolkit/REPOSITORY_EVALUATION.md#evaluate-selection-independently)

Advance source-bound candidates through the existing protected grader
preparation and reference/counterexample checks. Keep development and formal
exposure disjoint, and keep repository families in one stage. Inspect rights
and compatibility before any task disclosure. Freeze the optional capability
configurations, ordinary tool inventory, verified score, usage measurements and
applicable metrics before running independent comparisons. Use the same
inventory, permissions and budget when evaluating pre-task AEEP selection
against discovery-only and a fixed policy derived from prior data. Include
decision overhead and preserve negative results. No cached lead authorizes
live execution or changes a formal threshold.

## Reproduce the read-only case audit

Run from the repository root. It verifies the existing private assets and
prints an aggregate result. Add `--private-leads` with a fresh path under
`.aeep` only to save the source-level candidate inventory.

```bash
PYTHONPATH=.aeep/sol-comparison-preflight-20261116/frozen-source/src \
  python3 -B reports/toolkit-v2/c13/completion-20261116/audit_formal_inputs.py
```
