# AEEP 0.5 DSH deterministic proof

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

The live DeepSeek Harness proof is a separate, explicitly approved campaign.
Its checked plan sends six synthetic turns through the model-facing AEEP MCP
bridge and validates only sanitized evidence (tool names/counts, hashes, AEEP
receipt IDs, and aggregate token buckets):

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

The comparison report uses six fresh read-only sessions to compare direct model
counting with one AEEP `text.stats` call. It records the observed correctness
gain and token overhead without treating the negative savings result as a
failure.
