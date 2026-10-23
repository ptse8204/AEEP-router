# Upstream source review and reuse decisions

October 19 telemetry correction: D65 reuses the existing Codex 0.154.0 native
OTLP collector and AEEP execution journal. No new telemetry dependency or hosted
backend is selected. All 564 old token captures passed a retrospective consistency
audit; provider metering trust is unchanged. Bounded snapshot retention and managed
reporting are implemented. A new worker-local collector profile still needs exact
boundary review and prospective conformance/live capture checks. See
[the telemetry guide](TELEMETRY_REPAIR.md).

C01 inspection, October 8, 2026. These are source pins, not installed or qualified
binaries. No third-party source was executed. Machine records in
[`reports/toolkit-v2/c01`](../../reports/toolkit-v2/c01/README.md) retain exact
file URLs, SHA-256 hashes, commit dates and latest-release responses. A release
label does not mean the inspected commit is that release.

## Selected evaluator path

Try a thin agent-skill-eval adapter first, with the existing AEEP controlled runner
as fallback. The inspected `runner.py` keeps treatment invocation optional unless
`force_skill_invocation` is set. Its workspace manager creates temporary Git trees;
its Codex harness directly launches `codex exec --sandbox workspace-write`.
Neither establishes AEEP's separate controlled-worker boundary. Its parser defaults
missing input/output counters to zero and retains only the final attempt output.
A wrapper must recover canonical events and missingness independently or reject
those metrics; it cannot qualify raw summaries as complete accounting.

Waza's inspected execution request uses Copilot SDK tools and permission handlers.
SkillRank's inspected treatment prompt forces skill use. Neither is a drop-in
natural-choice Codex evaluator. Their optional roles remain visible.

## Pinned component matrix

All runtime compatibility, exact installed host versions, footprint, transitive
license closure and rollback behavior below remain UNQUALIFIED until an executable
adapter check. “DEFER” is a component design decision, not an operator deferral of
its checkpoint. No mutable-HEAD installer is approved.

| Component/source pin | Decision | Observed license scope | Interface, dependencies and unresolved boundary |
|---|---|---|---|
| [tardigrde/agent-skill-eval @ 59de161f657b](https://github.com/tardigrde/agent-skill-eval/tree/59de161f657b82bfaf8f6abe83dfff38552deb21) | WRAP candidate | MIT | Python >=3.11; CLI JSON artifacts, Codex/Claude/OpenCode subprocesses. Typer/Pydantic/OpenAI/Rich/PyYAML/dotenv. Optional skill prompt supported; temporary Git workspace is not independent containment. |
| [microsoft/waza @ 774df00a4f04](https://github.com/microsoft/waza/tree/774df00a4f04fb5d193548a2cf3f45470fe285bb) | DEFER | MIT; bundled CLI separate license | Go CLI; Copilot SDK types in ExecutionRequest. Bundled Copilot CLI extracts to cache. Other engine portability needs proof; do not install for first Codex evaluator. |
| [buildbetter-app/skillrank @ 5216bae9149b](https://github.com/buildbetter-app/skillrank/tree/5216bae9149b4ff8a7f9e014b6889fb094cee8e1) | DEFER evaluator; optional catalog candidate | MIT crates; Elastic-2.0 registry/web | Rust CLI/core. Agent runner forces treatment invocation, truncates CLI version to major.minor, defaults failed usage fields. Direct launch and timeout child kill need containment/accounting review. |
| [benchflow-ai/skillsbench @ 9a1f4dd5f765](https://github.com/benchflow-ai/skillsbench/tree/9a1f4dd5f7659f75707435da3ce854b6e48321d1) | REUSE selected existing adapter | Apache-2.0 repository; per-task rights still review | Harbor/Docker task, solution, verifier directories. Existing AEEP DOCX adapter/recipe already available; preserve historical negative study and original source pin. |
| [eval-sys/mcpmark @ cd45b7f57923](https://github.com/eval-sys/mcpmark/tree/cd45b7f57923b9b3985467f5139927575f83141c) | DEFER | Apache-2.0 repository; service/data terms separate | Python pipeline; external MCP services and credentials vary by task. Verified task revision supersedes old scoring. Import only selected pinned tasks after license and verifier review. |
| [SalesforceAIResearch/MCP-Universe @ 0df6c42717f2](https://github.com/SalesforceAIResearch/MCP-Universe/tree/0df6c42717f2a618d34f5b271efd05be462b9e4d) | DEFER | Apache-2.0 LICENSE.txt; task/asset terms unknown | Python >=3.10; Dockerized MCP servers and benchmark modules. Requires service-specific credentials and setup; too much surface for Essentials. |
| [ALEX-nlp/OpenSkillEval @ d0e109283eee](https://github.com/ALEX-nlp/OpenSkillEval/tree/d0e109283eee79216284cdf09ee59bf63239fb13) | DEFER data; research reference | Apache-2.0 code; CC-BY-NC-4.0 dataset | Python runner with artifact tasks and model/VLM judging. Dataset redistribution excluded from commercial bundle; judge spend and worker conformance unknown. |
| [cisco-ai-defense/skill-scanner @ c3d7fd9fee50](https://github.com/cisco-ai-defense/skill-scanner/tree/c3d7fd9fee50cf2ea45f0b381eb61f857360f825) | WRAP optional candidate | Apache-2.0 | Python >=3.11 CLI/SDK. Static and model-backed analyzers have different network/credential/cost requirements. Findings are risk evidence, not safety or containment. |
| [modelcontextprotocol/registry @ 970df037919f](https://github.com/modelcontextprotocol/registry/tree/970df037919faa70456dde08c295473002d850e5) | KEEP existing client | Apache-2.0/MIT transition; docs CC-BY-4.0 | Use existing bounded /v0.1/servers client. Hosting Go/PostgreSQL registry is unnecessary; discovery grants no execution authority. |
| [open-telemetry/semantic-conventions @ 68e89181d4cb](https://github.com/open-telemetry/semantic-conventions/tree/68e89181d4cb9bbce975c8128e694363214ab5fb) | REUSE conventions | Apache-2.0 | Keep installed OTel API; pin semantic interpretation in adapters. Exporter destination/privacy and GenAI field stability require C10 review; no server needed. |
| [langfuse/langfuse @ c106bb3d9453](https://github.com/langfuse/langfuse/tree/c106bb3d945323688e6f6079f65fb0ab28203b53) | DEFER external exporter | MIT except ee paths; third-party terms separate | HTTP/SDK observability integration; self-hosted multi-service stack is optional. Prompts/output must remain excluded unless explicit consent. |
| [Arize-ai/phoenix @ 4b1fa58bc7d6](https://github.com/Arize-ai/phoenix/tree/4b1fa58bc7d6bd4d43d4034bac9a9a2a1def79a4) | DEFER external exporter | Elastic-2.0 server | OTel observability server, not required core. License limits hosted/managed service use; no assumption of MIT packaging. |
| [stacklok/toolhive @ 33ba170aad63](https://github.com/stacklok/toolhive/tree/33ba170aad633e20520f380500a45cd158f24aed) | DEFER runtime adapter | Apache-2.0 | Go CLI with Docker/Podman MCP runtime, OIDC/OAuth and exporters. Container availability does not prove AEEP worker/credential separation. |
| [langchain-ai/langgraph @ 40a2e6d84505](https://github.com/langchain-ai/langgraph/tree/40a2e6d845054cc0cc17a6a169ca6e7394e5231c) | DEFER workflow adapter | MIT | Python graph API; dynamic durable workflows differ from serial AEEP DAG. Retain external bounded execution until mappings and authority checks exist. |
| [ANative-Lab/EvoAgentX @ d77fd6b9a3e7](https://github.com/ANative-Lab/EvoAgentX/tree/d77fd6b9a3e76c8dd83bebe3374c53a3f5d16f54) | DEFER proposer | MIT | Python model-backed workflow generation/optimization; API keys and generated code require separately bounded execution and cost authority. |
| [FoundationAgents/AFlow @ 3f457218fc71](https://github.com/FoundationAgents/AFlow/tree/3f457218fc716093fe53f6df8a5d5e6379d66346) | DEFER optimizer | MIT | Python run.py optimizer for selected datasets; model-driven search is metered. No need to duplicate it inside core; data/dependency rights unknown. |
| [microsoft/agent-framework @ 2d9cc3f8ae46](https://github.com/microsoft/agent-framework/tree/2d9cc3f8ae465baf1aed3022f89b6848db4ffa7b) | DEFER executor | MIT | Python/.NET provider SDKs and workflows. External bounded adapter only after version and permission compatibility; does not replace evidence layer. |

## Restored handoff entries

The original matrix also contained these two rows. They were omitted when the
C01 research table replaced it. Their roles below come from the handoff; this
audit does not establish new upstream compatibility or license facts.

| Component | Handoff role | Current evidence and disposition |
|---|---|---|
| [Archestra](https://github.com/archestra-ai/archestra) | Research competitor or external integration; already DEFERRED in the ZIP | Restore as deferred research, not a default package. The handoff flags AGPL/enterprise terms; exact source, license and compatibility remain unverified. |
| [GitHub Sponsors](https://github.com/sponsors) | External authorized support link | Restore the C12 support target. Developer attribution, authorized links and applicable eligibility remain unfinished; no local payout service is proposed. |

## Existing software retained

- AEEP `BenchmarkRunner` and `AssessmentService` at
  `8b015bf0247d4d9f49038982c49f3711a2802d97`: REUSE as fallback. Existing reviewed
  definitions, operation accounting, independent grading and controlled workers
  reduce migration risk. It imports Router internally; C06 must distinguish
  internal reuse from requiring users to configure routing.
- ARD: KEEP the adopted v0.91 source pin
  `b76f235a8f461876ad4f1e77abd0eb0eb302b48d`, Apache-2.0, under
  [ADR-010](../adr/ADR-010-ard-discovery-boundary.md). New upstream commits do not
  silently change this contract.
- Router/StackRuntime, Codex/Claude/DSH connections, component setup, local OTel
  and economic attribution: KEEP/WRAP as described in [INVENTORY.md](INVENTORY.md).
  No second approval, execution, installation or evidence database is proposed.

## Qualification still required

C04 must check actual host flags, optional exposure, independent graders,
interruption and incomplete usage before enabling the chosen evaluator. C03 must
resolve the complete selected dependency graph with exact artifacts, licenses,
permissions and measured or unknown resource requirements. Source versions and
README platform claims do not establish either gate. Open issue triage, installed
host compatibility and transitive binary licenses remain unknown; nothing here
permits installation. The first fallback remains AEEP even if an external spike
fails; record a switch before a campaign, never during one.

Research-only scratch files are retained at
`/tmp/aeep-toolkit-v2-source-review`; they are not a dependency, executable path or
vendored source. Re-fetch using the immutable URLs and verify the recorded hashes
if that temporary directory is gone.

## Subsequent C04 executable development evidence

The operator requested an actual consolidated stack after reviewing the bounded
fixture setup. The agent-skill-eval 0.7.0 wheel, SHA-256
`5e29aff9fc354475c7e3e652659475e89cbb438603ee55d0392f0c845dbcf07f`,
matches all 16 reviewed Python source files. The
[development stack](../../integrations/toolkit/README.md) installs a full
24-wheel closure in a private environment and runs the actual upstream CLI,
fake harness, deterministic graders and Markdown report. A fresh rebuild also
completed the four expected synthetic trial records. No upstream source patch
or vendored runner was needed.

The first invocation exposed a zero-exit/all-trials-error behavior; its artifacts
are retained. The AEEP bridge independently checks expected records and fixture
outputs before presenting success. Source, package and output hashes are in
[the C04 summary](../../reports/toolkit-v2/c04/stack-summary.json). This qualifies
the fixed local engineering demo only. Controlled real-host dispatch, general
normalization, canonical accounting and comparative model value remain unqualified.

## Operator-restated integration scope

D20 records the operator's 14 component assignments in
[the architecture map](ARCHITECTURE_LOCK.md#operator-specified-component-map).
The C01 table's DEFER entries describe the initial evaluator selection; they do
not remove those optional integrations from the implementation plan. Waza,
SkillRank core, the MCP benchmark packs, ToolHive, observability and workflow
adapters remain separate targets with unfinished compatibility checks.
GitHub Sponsors is the initial external developer-support mechanism; no local
payment service is required. A developer-specific link still needs attributable
source evidence before the report offers it.

## C01 required decision worksheet (complete for every mandatory candidate)

- Canonical upstream URL, release and commit SHA; last maintenance, open issues relevant to selected integration.
- License of code, benchmark datasets, registry, assets and transitive packages, with compliant redistributability summary.
- Exact host CLI/SDK versions supported, OS, architecture and authentication model; verify in installed environment.
- Exposed entry point: library import, subprocess CLI with machine output, JSONL protocol, MCP or HTTP.
- Supported candidate types: `SKILL.md`, MCP, plugin bundle, API, arbitrary executable (not all should be assumed equivalent).
- Comparison semantics: natural selection vs forced; ordinary tools visible to both arms; controls for state, outputs, evaluator independence, permissions and context.
- Observed metrics and missingness: token categories, wall clock, source, actual/estimated cash, retries, failures, tool exposure/usage.
- Side-effect containment, setup/teardown, crash/restart, parallelism, resource limits, test cost.
- Dependency footprint and user install preview data; rollback/uninstall constraints.
- Integration proof: offline conformance or real-host evidence and exact logs; status YES/NO/UNKNOWN, not marketing copy.
- Final choice: REUSE (existing AEEP), WRAP (external), REPLACE, KEEP, ARCHIVE, or DEFER, with rationale, risks and migration plan.

## Principle

A package being open source does not imply its hosted service, datasets, benchmark tasks or pretrained assets can be bundled or sold. Optional adapters can interface with externally installed software without redistributing its implementation; still check interface terms and user consent.

## Restored worksheet reconciled

[The completed source-review worksheet](../../reports/toolkit-v2/c01/review-worksheet.json)
addresses all eleven required fields for each of the original 21 responsibilities,
including the two existing AEEP roles, Archestra and Sponsors. ARD retains the
separate adopted pin in ADR-010. Source pins, release observations and maintenance
dates remain distinct. Unknown installed compatibility, binary dependency rights,
footprint and rollback are explicit; they block installation/qualification, not
recording the source-selection decision.

The [bounded issue review](../../reports/toolkit-v2/c01/issue-triage-20261008/README.md)
retains the first 30 recently updated open issue/PR entries for each of the 17
external repositories. Reports about Waza sandboxing, benchmark verifier/reset
behavior, workflow retries/shared state and telemetry interpretation identify
checks for future adapters. These are upstream reports, not reproduced defects
at every pinned revision. An empty page or selected-issue list is not a clean
bill of health.

The first-evaluator comparison remains:

| Candidate | What supports reuse | Why it is or is not first |
|---|---|---|
| agent-skill-eval | Actual pinned CLI, optional skill exposure, both fake-harness arms and deterministic graders now execute; existing AEEP command executor/store record the coordinator | Preferred external candidate. Keep its scheduler; connect separate workers and complete host accounting before live use. |
| Waza | Source exposes evaluation/custom-agent workflows and a mock engine | Optional next evaluator. Reviewed execution types use Copilot SDK; exact Codex compatibility and containment remain unproved. |
| SkillRank core | MIT local core/search with a separate registry license | Optional discovery/evaluation integration. Inspected treatment forces invocation, so it cannot supply the primary natural-selection experiment unchanged. |
| AEEP BenchmarkRunner | Existing controlled workers, frozen plans, independent grading and durable budgets/receipts | Explicit fallback if external requirements cannot be met. No fallback campaign has been started or switched mid-run. |

The [recorded fixture run](../../reports/toolkit-v2/receipt-showcase/report.md)
now exports C02 evidence plus one canonical coordinator receipt. The local
resolver checks the receipt, immutable record snapshots and artifact hashes.
The receipt covers the evaluator process, not per-trial model accounting.
C04 remains unfinished; this does not establish general `EvaluatorAdapter`
dispatch, controlled workers, live-host compatibility or benchmark benefit.

The Waza release metadata check also resolves the exact macOS arm64 asset hash
and tag source under `reports/toolkit-v2/c01/waza-release-*.json`. The observed
0.38.9 release tag points to `e534d149d89ae77ea158469fb4d2003804b2ee76`, not the
reviewed branch pin `774df00a4f04fb5d193548a2cf3f45470fe285bb`. Retain that distinction
when preparing a binary spike; neither the release label nor a nearby source
commit proves the binary's compatibility. No Waza archive was downloaded,
installed or executed by this metadata check.

## Installed-payload hash gap observed in C04

The pinned 0.7.0 `SkillInstaller` copies nested `evals`, `.git` and cache
directories while excluding them from its content hash. The sandboxed synthetic
probe in `reports/toolkit-v2/c04/nested-payload-probe` reproduced the mismatch;
an unpublished issue draft accompanies it. The fixed AEEP demo now stages only
two manifest-bound files and rejects unlisted entries. General candidate payload
identity needs its own adapter check or a reviewed upstream correction before
qualification. This finding leaves the preferred candidate selected and its
live/controlled-worker status unqualified.

## October 9 per-trial integration proof

The actual pinned agent-skill-eval scheduler and graders now dispatch the fixed
fake harness through AEEP ContainerExecutor. The trusted parent reserves before
each trial, retains an individual receipt and durable events, and validates the
current case/arm. Worker source is outside the coordinator's writable sandbox;
the coordinator has no Docker socket. Both arms use the same pinned image, Python
and shell. These facts establish the fixed synthetic dispatch path, not capable
Codex conformance or safe arbitrary candidate execution.

Five bounded engineering replays retain 20 trial workers and their operation
charges under `reports/toolkit-v2/c04/controlled-trials`; cleanup inspection found
none remaining. Later replays repair redaction, event persistence and source
staging, then bind existing AEEP analysis. The final read-only verifier rejects
altered summaries, artifacts, receipts, events and accounting. Model measurements
and cash remain unknown. General candidate inspection now hashes exactly the
payload it stages, excluding nested evals/Git/cache directories from both.

## October 9 captured-candidate replay

The configured adapter now uses the same pinned scheduler and grader with a
captured `SKILL.md` tree, including resources. Its treatment workers independently
rehash the staged payload. The three-case public fixture and a separate default
privacy replay completed 12 workers, with all workers removed. Exact source
hashes, arguments, receipts and audits are under
`reports/toolkit-v2/c06/offline-journey`. The primary upstream remains selected.

This adapter implements the C02 interface for scripted offline execution. A model
does not interpret the candidate; Codex compatibility remains unqualified. No
fallback campaign or new optional-engine installation was started.

## October 9 managed-backend selection after executable contract checks

The installed 0.7.0 Codex parser and command builder were exercised without
launching Codex. Missing primary usage became zero; the default command inherits
the caller environment and has no paired managed-worker binding. The exact
synthetic observations and pins are under
`reports/toolkit-v2/c04/codex-harness-contract`. This does not assert that an
actual credential leak or model failure occurred.

D40 selects the existing AEEP AssessmentService/BenchmarkRunner fallback for the
first managed-model adapter. Agent-skill-eval remains the working scripted
backend. No live campaign has begun or changed engine. AEEP's existing App Server
parser also needs D41's partial-usage correction before qualification; fallback
selection is not a conformance PASS. The managed adapter is integrated and passed full software checks on `40a8b7a`. It reuses the existing service, grants and workers; four fresh zero-turn native command workers passed. Actual V2 managed-model qualification remains open.

## October 9 executable and source follow-up

- Agent-skill-eval's explicit CLI completed six fresh synthetic trials on source
  `5386064`, with verified receipts, default content minimization and exact worker
  cleanup (`reports/toolkit-v2/c06/verified-journey`). Native Codex remains the D40
  fallback path; these results do not change upstream native qualification.
- Existing DiscoveryService passed an inert local replay with source authority
  enforced (`reports/toolkit-v2/c08/local-discovery`). Cisco remains source-only.
- Waza release 0.38.9 points to `e534d149d89ae77ea158469fb4d2003804b2ee76`,
  distinct from the C01 source pin. The four inspected execution/CLI source files
  match byte-for-byte across those commits. Its exact Darwin/Linux arm64 archive
  metadata is retained, but no binary was downloaded or executed; binary/source
  correspondence and runtime qualification remain open (`c09/waza-review`).
- Installed OpenTelemetry API 1.44.0 produced a non-recording span with no trace ID
  in a fresh default process (`c10/telemetry-audit`). This is not an exporter audit
  or evidence that all measurements are available.

### Pinned candidate provenance and support follow-up

Ponytail tag v4.10.0 resolves to `1d95ff7d39de12d87014ea40d4e22201bddc501b`.
Its skill file hash matches the existing selected worker's
`1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2`.
The pinned package declares DietrichGebert as author and MIT licensing; its
FUNDING.yml supplies GitHub Sponsors account DietrichGebert. Exact URLs, hashes
and a validated source/developer assertion are in `c12/developer-source`. This
is attributable repository metadata, not legal ownership or payment verification.
The host currently has Ponytail 5.1.0; these pins and historical studies do not
apply to that newer installed version. No candidate code was executed.

## Integration completion update (October 9)

The [current dispositions](../../reports/toolkit-v2/integration-completion/README.md)
and [21-responsibility review update](../../reports/toolkit-v2/integration-completion/upstream-review-update.json)
apply over the immutable C01 worksheet. Four actual LangGraph fixtures and six
Waza mock outcomes now have pinned executable evidence and cleanup records.
Cisco report import, configured discovery and local OTLP preview are implemented;
their scope does not imply installed scanner/exporter/deployment conformance.
The update records specific task-mapping, data-rights, optional-choice and
execution-boundary reasons for excluded integrations. Original source reviews,
failed attempts and historical live results retain their original meanings.

### October 15 installed-path verification

The exact `d2c406f` package passed 15 sandboxed offline CLI checks, including
configured discovery, Waza import and local trace/export previews. Its private
runtime was removed unchanged. [The installation record](../../reports/toolkit-v2/integration-completion/package-review-schema-correction/execution/summary.json)
updates package compatibility only; it does not qualify upstream scanners,
remote exporters or additional host platforms. Waza and LangGraph retain the
previously recorded bounded executable evidence. No upstream version changed.

### October 19 managed-worker readiness failure

No upstream pin or production source changed. The prepared three-family managed
qualification stopped on its first host preflight rejection. A separately charged
zero-model probe reproduced a `CodexRequestError` at `account/rateLimits/read` in
the existing Codex worker. This does not establish a new defect in agent-skill-eval,
Waza, the candidate or the comparison math. The underlying capacity, connectivity
or API cause remains unknown. [The current record](../../reports/toolkit-v2/integration-completion/resumption-20261019/README.md)
supersedes earlier storage-only readiness descriptions. Resolve the worker before
reviewing a fresh campaign; no backend or model substitution is authorized by
this failure.

### October 19 readiness repaired; no upstream pin changed

The existing model proxy was OOM-killed under its 128 MiB cap. The reviewed
512 MiB/no-swap cap passed network health and restored both workers' readiness,
pinned model and existing identities. A separate public connectivity turn
succeeded. No Codex binary, upstream evaluator, image or dependency changed.
The editing preparation had also lost the already supported prompt output mode;
new definitions restore it in both arms and have fresh paired boundary evidence.
[The repair record](../../reports/toolkit-v2/integration-completion/worker-readiness-repair-20261019/README.md)
keeps the first-trial failures, measurements and inference limits separate from
qualification and optional-access value results.

The October 19 generated editing-tool validation added no upstream dependency or
version change. It uses standard-library Python in the existing pinned runtime;
its 28-input result is training evidence only. The source/usage hashes and two
exact derivative image IDs are recorded under
`reports/toolkit-v2/c07/edit-reusable-20261019`. The approved packaging correction
uses existing chmod and does not install software or execute the generated tool
during image construction. Optional model use still requires frozen value-stage
definitions and current boundary evidence.

The value metric audit changes no upstream pin or adapter. It corrects native
metric identifiers while retaining provider_report/self_asserted token provenance.
That evidence is insufficient for independent token-saving admission, even when
all protocol counts are present. Fresh value trials reuse the already-qualified
profiles; qualification and conformance are not repeated for this definition fix.

The corrected optional-use comparison is now complete through the existing AEEP
fallback:564 valid actual Codex task runs,105 holdouts per arm, zero receipt gaps,
source unchanged. Candidate wall bounds do not establish the frozen 10% benefit;
strict token evidence and candidate-use telemetry remain unavailable. This adds
bounded live comparison evidence without qualifying the upstream Codex harness,
scanner, hosted telemetry, benchmark packs or other host platforms. No upstream
pin changed. See the [four-arm result](../../reports/toolkit-v2/c07/edit-value-native-20261019/comparison.html).

### October 20 local time — capture bundle exposed stale image collector

No upstream pin or dependency changed. The corrected AEEP wheel passed 15 offline
CLI checks and one retained-capture check with its 32 unchanged dependency pins.
The exact 67-file offline documentation check passed; both private runtimes were
removed. The collector check failed before model dispatch because the two pinned
images contain an older collector than their newly reviewed file guard permits.
The existing native OTLP implementation remains selected; the proposed correction
copies its already-reviewed current bytes into two small derived image layers.
[The exact repair](../../reports/toolkit-v2/c07/capture-image-repair-20261020/README.md)
needs approval because the preceding bundle excluded builds and replay. No new
backend, credential setup or model destination is required. The old study and
its independently unverified provider counts remain unchanged.

### October 21 — builder source-reference failure; no upstream change

The operator-approved COPY-only collector image attempt failed before creating an
image. Bare sha256 FROM syntax became a Docker Hub source name and triggered a
failed metadata lookup. No worker, collector or model started. The reference-only
amendment uses the same parents' existing local repository digest names; both
resolved correctly under read-only inspection and have no ONBUILD commands.
[The prepared amendment](../../reports/toolkit-v2/c07/capture-local-parent-20261021/README.md)
requires approval under the prior no-retry rule. No upstream version, dependency,
collector source, model or destination changes. The completed package/docs results
and original comparison remain unchanged; live collector behavior is unqualified.

### October21: current-source installation passes; no upstream replacement

The current7707756 wheel passed15 offline CLI checks and1 retained capture-chain
check with32 unchanged cached dependency pins and no downloads. Its private runtime
was removed. The12 integrated source checks passed. No upstream version or license
changed. Collector packaging failed local-parent resolution in BuildKit before
worker/model execution; local image inspection did not predict that resolver result.
The pinned docs attempt stopped at a blank-line lint error before its link scan;
formatting is corrected and Markdown lint passes. The proposed
[local-tag/docs amendment](../../reports/toolkit-v2/c07/capture-local-tag-20261021/README.md)
keeps parent IDs, collector bytes and Lychee0.24.2 unchanged. It is not yet executed.
No dependency/framework change, hosted service or credential intervention is needed.

### October21: existing native OTLP path verified through real captures

No upstream pin, license or dependency changed. Two current collector images built
and passed11-group containment with collector access denied. Three real model
receipts have verified journal/token-capture consistency; the corrected pair passed
independent task grading. The provider counts retain their original trust tier.
Actual metric batches arrived, but no positive candidate injection was captured.
A required-input probe failed its stale runtime identity before model dispatch;
a fresh model-free required profile now passes. Its1-turn positive-check authority
is pending because all4 earlier reservations remain charged. See
[the current evidence](../../reports/toolkit-v2/c07/capture-explicit-profile-20261021/capture-status.md).
The same Lychee0.24.2 offline docs check passed. No hosted observability stack,
new evaluator or framework is needed for this correction.

### October 21 completed positive diagnostic — no upstream change

Four actual model token capture chains verify. A bound native positive injection
event confirms reviewed Ponytail instructions loaded in the forced extra turn.
Optional selection and semantic contribution remain unknown; provider reports
retain their trust tier. Both current profiles pass containment. Source `7707756`,
agent-skill-eval/Waza/LangGraph pins, existing native OTLP and Lychee 0.24.2 are
unchanged. No hosted backend, new package or architecture is needed for the fix.
The original value study is still INCONCLUSIVE. See [the completed capture
handoff](../../reports/toolkit-v2/c07/capture-explicit-profile-20261021/README.md).

### October 21 C13 resource proposal — existing stack and controls

The production recommendation retains the existing local CLI, scripted
agent-skill-eval, managed fallback and on-demand workers. Installed psutil 6.1.1
and Docker instrumentation remain selected; official documentation was consulted
for CPU priming, cache fields and VM state, with no upgrade or service change.
[The proposal](../../reports/toolkit-v2/c13/production-readiness-20261021/PRODUCTION_WORKLOAD.md)
sets prospective targets. Two first-party control-help commands passed, not a new
upstream/model qualification. No previous optional adapter disposition changes.

### October 21 value/selection steering supersedes resource-first sequencing

No upstream pin or adapter disposition changed. Keep agent-skill-eval's actual
scripted scope, the managed fallback and existing policy/recipe/worker/report
infrastructure. Comparative usefulness and selection behavior are now the critical
path; infrastructure checks do not qualify either. New real-task snapshots,
grader mapping and independent cases still need review. The prior 30-command/
12-turn resource proposal is historical, not scheduled; arbitrary numeric SLOs
are not adopted product requirements. See [the corrected priorities](../../reports/toolkit-v2/c13/value-priority-20261021/PRIORITIES.md).

### October 21 repository grading and selection implementation

No upstream package pin changed. The managed path reuses the recorded
agent-skill-eval Codex fallback: `AssessmentService`, `BenchmarkRunner`, recipe
extensions, controlled containers and canonical receipts. Extension v4 adds
protected repository behavioral grading; it does not replace the runner.
Selection reporting uses the existing route-decision contract and scientific
analysis remains in the existing assessment reports. Waza, LangGraph, routing
and other optional integrations retain their recorded scope.

Three Apache-2.0 source-pinned AEEP adaptations are development examples only.
The new code does not qualify their worker boundary or establish any capability's
benefit. Source tests are running; one exact no-model review will cover contained
grader checks, the changed wheel and the existing pinned offline documentation
checker. Independent real-task holdouts and live comparison remain open.

### Repository-workload source follow-up

The pinned SWE-bench harness LICENSE confirms MIT. The pinned Verified dataset
card lists 500 issue/PR pairs and gold/test fields but has no license declaration.
Underlying repository and dataset rights still need a task-specific review before
adoption or redistribution. No task rows, test harness or upstream code were
executed; no holdout cohort was selected. The bounded callable grader is not a
full-repository SWE-bench adapter. Exact read-only source hashes and exclusions are
in `reports/toolkit-v2/c13/repository-audit-correction-20261021/independent-upstream-followup.json`.
Agent-skill-eval and the recorded managed-path fallback remain unchanged.

### October 22: pinned SWE-rebench task/grader preparation

The preceding correction bundle passed its 23 contained development observations,
18 installed checks and pinned offline docs scan; no upstream engine disposition
changed. Source5f4e318c remains the verified executable source.

Read-only source review now covers `nebius/SWE-rebench-leaderboard` revision
`34d5a58864acf91613740a09ec5d205228dcfa39` (dataset CC-BY-4.0; underlying repository
licenses still apply), and its recommended MIT-licensed harness fork
`SWE-rebench/SWE-bench-fork` at `980d0cca8aa4e73f1d9f894e906370bef8c4de8a`.
The 860-row union has 413 repositories. Monthly splits are overlapping partitions,
not additional independent cases. Public recency does not prove uncontaminated
model evaluation. No cohort is frozen. Exact source/response hashes and caveats
are in `reports/toolkit-v2/c13/repository-cohort-20261022/`.

One Loguru development task uses base commit
`2abeb0fa6d7be4b0455c6e0b580b1e9dab19005e`, with an exact MIT license and archive
hash. A prepared compatibility check reuses ten unchanged upstream function/enum
bodies, the real selected test module and 24 upstream test identities. It has
three source variants and three containment/state probes. Seven pinned cached
pure-Python wheels are inert; pytest8.3.5 instead of the suggested8.4.1 is a
declared transport-driven adaptation, not an upstream equivalence claim.
External code has not executed. Exact review56ca1751 is pending approval.

The current callable-snapshot grader is not a full-repository pytest adapter.
A successful development check must be followed by pack integration, task/runtime
validation and fresh controlled-worker conformance before model qualification.
Keep the recorded agent-skill-eval fallback and optional Waza/LangGraph scopes.
Do not install the entire SWE-bench dependency closure or pull mutable x86 images
merely to run this bounded development check.

### October22: upstream compatibility passed; reusable suite pack under verification

Actual approval56ca1751 was exercised once. Six fresh offline calls passed: three
containment/state probes and real Loguru unchanged/published-repair/regression
variants against24 upstream test identities. Eight canonical operations charged
10.433598458301276 seconds; model usage stayed3744 turns and cash0.0. Six
completed attempts/receipts and physical container cleanup were independently
reopened/checked. Exact evidence is in
`reports/toolkit-v2/c13/rebench-grader-20261022/completion-audit.json`.

The reusable v5 suite implementation now packages exact MIT-licensed TestStatus
and parse_log_pytest bodies at the same upstream980d0cca pin, with license and
body hashes. It uses standard pytest and exact cached wheel bytes in the existing
grader boundary. The evaluator fallback, Waza, LangGraph and optional extension
dispositions do not change. No upstream software was installed in this step.

Source573257b2 is undergoing full verification. This is a pack integration under
verification, not fresh external v5 conformance or an official SWE-rebench image
reproduction. Comparative usefulness, selection quality and resource acceptance
remain separate. Additional real development cases can be prepared as inert data;
their software cannot run under the terminal one-task approval.

### October22: current v5 source verified; three-case execution prepared

Source `fcd91dde` passes all thirteen configured source checks, 1,658 tests in
each full run, both coverage gates and nine retained proof checks. All thirteen
Node tests pass. The first source run stopped after a needed src-layout correction;
its incomplete record is retained. The current source terminal record is
`reports/toolkit-v2/c13/repository-suite-integration-20261022/validation-v2/source-stability.json`.

The prepared v5 cases reuse real Loguru, Click and Marshmallow upstream tests.
Loguru is MIT, Click BSD-3-Clause and Marshmallow MIT; task metadata is CC-BY-4.0.
Pinned official pure wheels add Click8.3.2, Marshmallow3.25.1 and simplejson3.20.1
as inert data. Embedded licenses and hashes are retained; nothing was installed
or executed from them. Reviewed source precedes wheel code; project wheels
supply version metadata. Python/pytest adaptations and omitted non-source edits
remain explicit. The source-only development tasks are not official benchmark
runs or a representative cohort.

Exact bundle `a2787cd8` awaits approval for changed-pack conformance, current-wheel
installation checks and pinned offline docs. All components are unstarted.
The agent-skill-eval fallback and other optional integration dispositions remain
unchanged. Comparative usefulness and live selection have no new evidence.

### October22 execution: three real repair/original pairs verified

The current v5 observer ran Loguru, Click and Marshmallow in the pinned offline
image. Published repairs passed912 required test identities. Original sources
failed11 declared bug tests while preserving901 existing identities. Click's
three nonrequired skips are separate. The Python/pytest adaptations remain
explicit; this is not official upstream image equivalence or model qualification.

The current wheel passed nineteen installed checks and pinned offline docs
passed. Both private runtimes were removed. Two terminal grader-review failures
are preserved: a report assertion on rejected pytest exit4, then a fail-closed
protocol error on the last Marshmallow import fault. Its raw reply was not retained,
so its malformed field and grade remain unknown. All twelve physical attempts
and receipts were independently reopened; owned containers are absent.

One reviewed semantic-fault replacement is pending at
`reports/toolkit-v2/c13/repository-suite-semantic-fault-20261022/operation-review.json`.
It changes deliberate source data and retains its next reply, with no product,
upstream dependency, image, model, installer or docs-checker change. Reproducible
independent cohorts and useful-capability/selection evidence remain open.

### October22: development conformance complete; new workload curation prepared

Actual approval `89245763` passed the new Marshmallow semantic-fault observation:
all 190 identities observed, all five repaired bug tests still passed,68
preservation failures and an invalid/test_failure grade. The bounded raw reply is
retained. Across three attempts all 13 canonical receipts were reopened; owned
containers are absent. Both earlier terminal failures remain preserved.

Eight provisional cases reuse pinned SWE-rebench issue metadata and real tests
from Python-markdownify, Python-Markdown, Mahjong, Dissect.cstruct, Mockito-python,
Files-to-prompt, Freezegun and Jsonpickle. Exact commits, archive hashes, individual
MIT/BSD-3-Clause/Apache-2.0 licenses and adaptation exclusions are retained in
`reports/toolkit-v2/c13/repository-screening-curation-20261022/prepared-cases.json`.
Metadata stays at `34d5a58864acf91613740a09ec5d205228dcfa39`; the reused MIT pytest
parser stays at `980d0cca8aa4e73f1d9f894e906370bef8c4de8a`.
Two cases are explicitly authored audits starting from published repaired source.
Official BeautifulSoup4.12.3 and Soupsieve2.6 pure wheels were cached as inert data,
with licenses and hashes; neither was installed or executed. Runtime reproduction
under Python3.13/pytest8.3.5 is unverified and needs the exact new execution review.
No upstream evaluator disposition, model result or admission changed.

### October22 completed reproduction : preserve workload exclusions; fix explicit plugin support

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

### October22: explicit plugin source verification completed

Current source `f694024c` passes all13 configured checks without drift:1673 tests
in each full run,21 skips,82% total coverage,both branch gates,Ruff,layering,mypy
and builds. Fifty focused tests and exact legacy serialization/observer equality
pass. Evidence is in `repository-plugin-support-20261022/validation`. No further
broad source test is needed on unchanged code. External plugin/runtime and current
installed-wheel conformance remain separate and unexecuted.

Late approval48fa60c0 is retained but unused because the review was already
withdrawn. The wider AST audit also corrects Dissect.cstruct and Mockito from
nominal multi-file edits to one executable source-file change each. Preserve their
actual test outcomes; do not use those labels to fill a balanced cohort. Genuine
replacement preparation and exact offline runtime/wheel/docs review continue.
No new model usefulness, selection, human-control,resource-acceptance or release
gate passes from these engineering checks.
