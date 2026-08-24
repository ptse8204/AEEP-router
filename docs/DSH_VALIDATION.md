# AEEP 0.5 DSH validation

The deterministic DSH fixture compares a model-suggested route, static AEEP,
signed shared evidence, and shared evidence plus local/cache adaptation. DSH is
a host/usage adapter—not a core routing dependency.

```bash
PYTHONPATH=src python examples/dsh_campaign/campaign.py
PYTHONPATH=src python examples/dsh_campaign/campaign.py --check
```

The proof uses the real signed provider-package lifecycle, reuses a 100-sample
prior, runs exactly two smoke executions, explicitly activates, and then routes
synthetic web/GitHub/document capabilities through the real Router. Hard gates
cover receipts, inert ingest, bounded smoke, deterministic valid execution, and
privacy. Performance and regret remain measured outcomes rather than required
marketing claims. The checked artifacts live in `reports/v05/dsh/`; synthetic
fixture token deltas are labeled separately from live Harness usage.

## Live DeepSeek Harness proof

The optional live proof is intentionally split into code review and execution.
`examples/dsh_campaign/live_campaign.py --check-plan` validates the six-turn
contract without starting DSH or calling a model. A live run begins only after
operator approval and uses the pinned local AEEP wheel through the DSH MCP
client.

The turns perform one AEEP tool call each: discover capabilities, execute local
text statistics, route a qualified file read, execute the read, repeat it in a
fresh session, and attempt an inactive patch capability that must fail closed.
Only the qualified read route is active during the run. The fixture directory
is read-only, and the route is suspended immediately afterward.

The sanitized report omits prompts, tool arguments, fixture contents, session
IDs, model output, and credentials. It keeps only tool names/counts, result
digests, AEEP receipt IDs, the verification-receipt hashes, aggregate
provider-reported token buckets, lifecycle counts, and hard-gate outcomes.
DSH token statistics are proof-host telemetry and are never imported as AEEP
observations.

`reports/v05/dsh/live-comparison.json` is the measured direct-vs-AEEP token and
correctness comparison. It excludes three pilot sessions whose prompts disclosed
the expected answer. The measured AEEP arm was more accurate but used more
tokens, and the checked report preserves that negative savings result.
