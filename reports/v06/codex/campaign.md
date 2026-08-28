# GPT-5.6 Terra Medium: direct Codex vs AEEP host-native routing

- Run date: 2026-08-28
- Codex CLI: 0.147.0
- Model: `gpt-5.6-terra`
- Reasoning effort: `medium`
- Suite: `aeep-06-live-codex-terra-medium-local-data-v1`
- Raw report SHA-256: `d405e5e544f3ca22bf121024ebc10f0a890562625e16acf8a8bc2d9701fa8df0`

## Result

| Measurement | Direct Codex | AEEP host-native |
|---|---:|---:|
| Measured tasks | 20 | 20 |
| Exact-output passes | 20/20 | 20/20 |
| Receipt coverage | 20/20 | 20/20 |
| Provider input tokens, total | 285,480 | 0 |
| Cached-input subset, total | 226,560 | 0 |
| Cache-write subset, total | 0 | 0 |
| Provider output tokens, total | 1,624 | 0 |
| Reasoning-output subset, total | 1,244 | 0 |
| Provider input + output tokens, total | 287,104 | 0 |
| Median provider input + output tokens | 14,356.5 | 0 |
| Median wall time | 5,976.5 ms | 6.48 ms |

Across the 20 matched pairs, AEEP reduced provider input-plus-output usage by a
median 14,356.5 tokens. A fixed-seed 10,000-resample bootstrap produced a 95%
interval of 14,349–14,363 tokens. The median paired latency reduction was
5,969.6 ms, with a 95% interval of 5,778.3–6,323.2 ms.

This is a demonstrated saving for one exact, deterministic, output-compatible
capability. It is not evidence that AEEP eliminates model usage for tasks that
need model judgment or lack a qualified substitute.

## What was compared

Both arms received the same `text.stats@1` action, input, and exact expected
output. Trial order was randomized with seed `60828`. Each arm ran ten times in
`process-cold` and ten times in `router-warm` conditions.

- **Direct Codex:** Codex performed the bounded calculation using GPT-5.6 Terra
  Medium. Terminal Codex JSONL supplied authoritative provider usage.
- **AEEP host-native:** AEEP evaluated the action before model execution and
  selected the already qualified, exact-schema local Python implementation.
  No provider request was needed.

The test validates the portable routing boundary, not a DeepSeek-specific
plugin. Codex is the host measured in this run; the AEEP decision and executor
contracts remain provider- and host-neutral.

## Accounting boundaries

- Installation consumed no provider tokens and is not part of execution usage.
- One warm setup per arm was excluded from measured summaries. The excluded
  direct setup used 17,949 provider tokens; the excluded AEEP setup used 0.
- Cached-input tokens are a subset of input tokens. Reasoning-output tokens are
  a subset of output tokens; neither subset is double-counted in totals.
- Subscription credits and actual cash were unavailable, not zero. No API-price
  counterfactual is presented in this campaign.
- The raw JSON stores resource/accounting evidence and receipt identifiers, not
  the action payload or model output.

## Reproduce

```bash
PYTHONPATH=src python3 -m aeep campaign run \
  @examples/proof/local-data-codex-terra-medium-suite.yaml \
  --manifest examples/proof/aeep.yaml \
  --database .aeep/codex-terra-medium-comparison.db \
  --output reports/v06/codex/campaign.json
```

Use a new database for a fresh campaign. Suite IDs are immutable and completed
trials are reused by design.
