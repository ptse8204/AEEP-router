# Upstream source review and reuse decisions

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
