# Subscription-aware routing

For operators exploring quota-sensitive selection. Install AEEP and run from
the repository root. The routing previews below do not invoke a model; managed
Codex execution is a separate, reviewed operation.

[Documentation index](../../docs/README.md).

This demo compares the current Claude session, represented as a host-owned subscription resource, with local execution. It needs no model API key.

```bash
aeep route text.stats \
  --manifest examples/subscriptions/aeep.yaml \
  --input '{"text":"hello from Claude"}'
```

Override current pressure without editing the manifest:

```bash
aeep route text.stats \
  --manifest examples/subscriptions/aeep.yaml \
  --input '{"text":"hello from Claude"}' \
  --context '{"subscription_quotas":{"anthropic.claude":{"state":"critical","confidence":1,"source":"user"}}}'
```

If a host route is selected, run it normally in the current agent and record the terminal outcome once with `aeep record` or `aeep_record_outcome`.

For an OpenAI/ChatGPT subscription managed by Codex, use the adjacent
`openai-codex-app-server.yaml` after replacing its absolute executable path:

```bash
aeep hosts codex doctor --manifest examples/subscriptions/openai-codex-app-server.yaml --json
aeep hosts codex models --manifest examples/subscriptions/openai-codex-app-server.yaml --json
aeep hosts codex quota --manifest examples/subscriptions/openai-codex-app-server.yaml --json
```

Those commands are non-billable diagnostics. Running the managed route starts
one Codex model turn, subject to both AEEP and Codex approval ceilings. The
example discovers models at runtime, stores neither prompt nor output, and marks
personal capacity `self_only`.

## Expected result and limits

Compare selected routes and rejection reasons between the two previews. The
quota override is a declared scenario, not a provider observation or a refund.
See [subscription setup](../../docs/BYOS.md) for credential ownership and
[accounting](../../docs/ACCOUNTING.md) for unknown versus zero usage.
