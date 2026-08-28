# AEEP 0.6 DSH proofs

This fixture compares a model-suggested route with static, shared-evidence, and
locally adaptive AEEP routing. It uses only local synthetic routes and stores no
prompt content. Reports are written to `reports/v05/dsh/` and cover static and
JS-rendered content, malformed-output fallback, unqualified routes, evidence
reuse, rate-card revaluation, cache reset/eviction, package tampering, and
fixed-seed route ordering.

```bash
PYTHONPATH=src python examples/dsh_campaign/campaign.py
PYTHONPATH=src python examples/dsh_campaign/campaign.py --check
```

The older three-arm files remain historical negative-control evidence for the
model-facing MCP design. They are not the ordinary AEEP integration.

```bash
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py --check-native-plan
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py --print-native-plan
```

The earlier six-turn MCP-only contract remains available to validate the
negative-control fixture and its checked reports:

```bash
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py --check-plan
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py --print-plan
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py \
  --check-report reports/v05/dsh/live-safety.json
PYTHONPATH=src python examples/dsh_campaign/live_campaign.py \
  --check-comparison reports/v05/dsh/live-comparison.json
```

Printing or checking the plan does not start DSH or make a model call. The live
run activates only the previously qualified read route, uses a read-only
synthetic fixture, expects the inactive patch route to fail closed, and
suspends the read route before report validation.

`plugin_campaign.py` implements `aeep-dsh-plugin-campaign-v2`: ten randomized
`DSH_DIRECT`/`AEEP_HOST_NATIVE` pairs for each of `web.page.read@1`,
`github.file.read@1`, and `document.text.extract@1` (60 fresh main sessions),
plus one excluded warm-up pair per capability. The provider sees the same
ordinary prompt in both arms. The native arm supplies the capability/input only
to the host command and exposes one canonical source schema; hidden target and
AEEP schemas never reach the model.

The script requires `--approve-live-provider-calls`, records a fixed seed,
preserves a supplied DSH Web PID, separates installation and warm-up data, and
emits the generated `schemas/dsh-plugin-campaign-report.schema.json` contract.
It reports disjoint provider token buckets, tool-result/schema pressure,
next-model-call input correlation, correctness, latency, and receipt coverage.
A savings claim is suppressed unless every hard gate passes and the 95%
bootstrap interval is wholly positive.

Copy and resolve the absolute placeholders in `cases.example.json`,
`direct.patch.example.yml`, `native.patch.example.yml`, and
`aeep-dsh-campaign.example.yaml` inside the separately approved DSH workspace.
The fixture plugin is `dsh-fixture-tools/`. Then run the live campaign only
after approval:

```bash
PYTHONPATH=src python examples/dsh_campaign/plugin_campaign.py \
  --cases /absolute/path/to/cases.json \
  --workspace /absolute/path/to/AEEP-dsh-test \
  --session-root /absolute/path/to/dsh-sessions \
  --direct-patch /absolute/path/to/direct.patch.yml \
  --dsh /absolute/path/to/dsh \
  --preserve-pid DSH_WEB_PID \
  --approve-live-provider-calls \
  --output /absolute/path/to/campaign-v2.json
```

The comparison report uses six fresh read-only sessions to compare direct model
counting with one AEEP `text.stats` call. It records the observed correctness
gain and token overhead without treating the negative savings result as a
failure. It does not prove that AEEP saves tokens.
