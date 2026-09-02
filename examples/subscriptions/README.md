# Subscription-aware routing

This demo needs no model API key. It represents the current Claude session as a host-owned subscription resource and compares it with local execution.

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
