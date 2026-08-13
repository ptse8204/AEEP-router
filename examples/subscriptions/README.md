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
