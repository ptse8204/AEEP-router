# AEEP 0.6 DSH validation

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

## Historical MCP negative control

The old three-arm plan remains available to reproduce the model-facing MCP
overhead finding. It is historical evidence, not the recommended integration:

```bash
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py --check-native-plan
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py --print-native-plan
```

The original six-turn contract remains as a compatibility and safety fixture.
`--check-plan` validates it without a model call. Its turns perform one AEEP
tool call each: discover capabilities, execute local text statistics, route a
qualified file read, execute the read, repeat it in a fresh session, and attempt
an inactive patch capability that must fail closed.

Only the qualified read route is active during that fixture. Its directory is
read-only, and the route is suspended immediately afterward.

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
It is evidence that model-facing routing has a cost, not evidence of token
savings.

## Host-native paired campaign

Use `examples/dsh_campaign/plugin_campaign.py` for the current live proof. It
runs ten randomized direct/native pairs for each of the web, GitHub-file, and
document-read capabilities: 30 pairs and 60 fresh main sessions. One warm-up
pair per capability is excluded. It requires an explicit approval flag and
never modifies or stops an already-running DSH Web process;
`--preserve-pid` makes process survival a hard report gate.

The native `/aeep` command validates the exact capability/input and live source
and target schemas before queuing the ordinary prompt. A persistent host bridge
holds the Router across the campaign. Only the canonical source schema reaches
the model. Transparent substitution requires exact output schema equality;
the sole reviewed adapter requires a true HTTP status and produces the exact
canonical `web_fetch` shape. The installed `dsh-read-url` remains disabled until
its real output supplies that status.

The report separates npm/DSH installation (zero provider tokens), excluded
warm-ups, and execution. It counts transmitted tool schemas as execution
pressure, keeps provider session usage authoritative, and claims savings only
when all hard gates pass and the fixed-seed 95% paired bootstrap interval is
entirely above zero.
