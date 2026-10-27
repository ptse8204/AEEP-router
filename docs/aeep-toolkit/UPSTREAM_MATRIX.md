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

### October22: approved plugin runtime and wheel/docs completed; one task scope remains

Actual review038b2af9 executed once on unchanged sourcef694024c. The25-wheel
local offline image build passed; exact image
`sha256:027b7b37d305b4904efb5a63059797818521df07b537cd403d145a362b61267e`
is retained at `aeep-toolkit-v2/repository-grader:py313-explicit-plugins-20261022`.
Parent layers/configuration match and recorded image-size growth is44342164 bytes;
this is not whole-host footprint or production resource acceptance. No old image
was deleted. Three fresh boundary/state/runtime probes passed. All22 physical
attempts/receipts were reopened, bounded replies retained and containers absent.

Seven cases reproduced. AbsaOSS and Foamlib each also reject both single-file
regressions of their genuine multi-file repair. Leanclient passed all14 declared
identities, but its module ran three additional real-Lean fixture tests that
returned ERROR. Its exit1 reference remains failed. Their detailed tracebacks
were not retained; static fixture requirements do not establish the exact exception.
The complete bundle remains failed rather than hiding this exclusion.

The build and calls charged25 operations/47.86661691684276 seconds. Grant counters
are12880 operations,3744 turns,118273.29034517473 seconds and0.0 cash. No model/cash
delta,refund or reusable terminal allowance. Installed wheel19 checks and cached
offline docs69 passed; both private runtimes were removed. Documentation evidence
binds its retained input hashes; later progress-only journal additions are separate.

A separately scoped Leanclient task now selects exactly the existing14 identities
through an appended protected collection hook. Public scope excludes unrelated
Lean-server tasks. All required assertions and zero-exit/missing/error/preservation
guards remain. Four inert payloads,18 assets,19 classifier regressions and four
synthetic guard cases pass preparation checks. Two inert preparation mistakes
(empty fault list/empty fault patch) are recorded; existing validators rejected
both. No product code changed or new upstream test executed during preparation.

Exact review7bbc9678 awaits actual execution approval: four offline observations,
six operations and290 reserved seconds on the same image,source,observer and
containment evidence. No builds,installations,package/docs reruns,models,cash or
release. This new task cannot retroactively pass the old whole-module result.
Full independent8/28/105 stages,capability qualification,usefulness,live selection,
human controls and workload-derived resource acceptance remain open separately.

### C13: declared-test approval completed; eight provisional screening cases reproduced

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

### C13: ten-repository batch completed; seven new candidates retained

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

### C13: compact patch transport verified; current execution bundle in preparation

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

### Compact repository runtime batch — October22 completed

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

### Repository corpus expansion — private Pydantic/Django grader supports

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

### Repository runtime batch completed — source59b9d61c

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

## C13: stale development fault diagnosed and corrected before new execution

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

## C13: corrected grader passed; task delivery and stop behavior failed

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

## C13: final source verification passed; exact execution bundle prepared

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

## Completed repository development journey, October 24

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

## Pending independent repository supports, October 24

[Five prepared task contracts](../../reports/toolkit-v2/c13/repository-independent-sources-20261024/README.md)
cover MSAL, SQLacodegen, LM Studio Python, Model Bakery and CanvasAPI. Their source
revisions, licenses and 16 optional support wheels are hash-bound in review
`be8b0e5f`. Static closure and 108 assets verified; no new runtime or upstream test
execution occurred. Do not label them qualified, adopted or installed. The existing
AEEP engine and container grader remain the execution stack.

## Independent runtime execution, October 27

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
