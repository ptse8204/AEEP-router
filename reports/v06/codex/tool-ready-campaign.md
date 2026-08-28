# Tool-ready Codex vs AEEP host-native routing

- Run date: 2026-08-28
- Codex CLI: 0.147.0
- Model: `gpt-5.6-terra`, medium reasoning
- Suite: `aeep-06-live-codex-terra-medium-tool-ready-v1`
- Raw report SHA-256: `9059dbf5478318ad337950901fa7a2d6227165eb6791e8afd53f1b537cbc0b8f`

## What this test answers

The exact deterministic implementation was already installed and known to both
arms. The test measures whether host-native AEEP can avoid the model loop for a
pre-classified action. It does not measure installation or ask AEEP to infer a
capability from natural language.

| 20 matched actions | Codex + exact tool | AEEP + same tool |
|---|---:|---:|
| Exact results | 20/20 | 20/20 |
| Verified local-tool executions | 20/20 | 20/20 |
| Receipt coverage | 20/20 | 20/20 |
| Provider input tokens | 581,689 | 0 |
| Cached-input subset | 557,056 | 0 |
| Provider output tokens | 2,760 | 0 |
| Reasoning-output subset | 821 | 0 |
| Provider input + output tokens | 584,449 | 0 |
| Median input + output per action | 28,888 | 0 |
| Median wall time | 8,324.9 ms | 5.47 ms |

The median paired token difference was 28,888 tokens (fixed-seed 95% bootstrap
interval: 28,869–28,901). The median paired latency difference was 8,319.1 ms
(95% interval: 7,426.4–9,299.0 ms). Cached input is a subset of input and
reasoning output is a subset of output; neither is added twice.

## Controlled setup

- Direct Codex was told the exact installed command and prohibited from search,
  inspection, or installation.
- A fail-closed JSONL check required exactly one successful invocation of that
  reviewed command in every direct trial. Only the count was retained.
- AEEP received the same `text.stats@1` input and exact oracle, then selected the
  same underlying Python function in process.
- GPT-5.6 Terra Medium, reasoning effort, input, oracle, repetitions, conditions,
  and fixed seed `60828` were held constant.
- Trial order was randomized across ten `process-cold` and ten `router-warm`
  pairs. One warm-up per arm was excluded from the table.

Installing a tool inside an agent makes it available; it does not remove the
provider call needed to choose the tool, read its result, and answer. AEEP avoids
that loop only when the host already has an exact semantic action. Open-ended or
model-judgment work still requires a model.

## Setup and excluded usage

Installation was not rerun or timed: Codex, AEEP, and the tool were already
installed. No installation command made a provider request, so installation
provider-token usage was zero—not an estimate of installation time or download
cost.

Provider tokens consumed while correcting and validating the campaign, but
excluded from the measured table:

| Excluded work | Input + output tokens |
|---|---:|
| Two compatibility pilots | 62,121 |
| First full run, rejected as insufficiently proven | 620,899 |
| Final campaign warm-up | 36,081 |
| **Total excluded provider usage** | **719,101** |

The final measured trials used 584,449 additional provider tokens. Total
provider usage caused by the complete correction run was therefore 1,303,550
tokens. This development overhead is not a per-user AEEP operating cost, but it
is reported so the experiment does not hide failed or excluded work.

## What this does not prove

- It does not show that all agent workloads become zero-token local actions.
- It does not compare clean-machine installation time or network bytes.
- It does not isolate individual Codex system, skill, or tool-schema tokens;
  terminal provider usage is authoritative only for the whole agent turn.
- It does not compare arbitrary catalogs. The direct arm knew the exact tool;
  exposing more tools can add context but was not varied here.
- It does not include actual cash: the route used a subscription channel and no
  reconciled billing amount was available.

## Reproduce

```bash
PYTHONPATH=src python3 -m aeep campaign run \
  @examples/proof/local-data-codex-terra-medium-tool-ready-suite.yaml \
  --manifest examples/proof/aeep.yaml \
  --database .aeep/codex-terra-medium-tool-ready.db \
  --output reports/v06/codex/tool-ready-campaign.json
```

Use a new database for a fresh run. Suite IDs are immutable and completed
trials are reused by design.
