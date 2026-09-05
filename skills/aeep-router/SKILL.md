---
name: aeep-router
description: Profile, compare, and safely execute equivalent agent actions across local Python, CLI, HTTP, MCP, and browser/computer-use routes using AEEP. Use before an expensive or repeated tool action, when context/compute/budget is constrained, or when choosing among multiple execution surfaces.
allowed-tools: Bash(python -m aeep:*), Bash(aeep:*)
---

# AEEP action router

Use AEEP at the bounded-action level. Do not send an open-ended objective such as "plan a vacation" as one capability. Decompose it into registered capabilities first.

## Workflow

1. Search capabilities progressively when uncertain:

```bash
python -m aeep search "current git branch" --compact
```

2. Check named subscription pressure when a host route may be used. For a
   reviewed Codex `host_managed` route, prefer the non-billable host diagnostics:

```bash
python -m aeep subscriptions status --compact
aeep hosts codex doctor --manifest aeep.yaml --json
aeep hosts codex models --manifest aeep.yaml --json
aeep hosts codex quota --manifest aeep.yaml --json
```

3. Route before executing when the task is expensive, risky, novel, or has several alternatives. Use the semantic compact response, not the full audit object:

```bash
python -m aeep route CAPABILITY --input '@input.json' --agent --compact
```

4. Inspect the selected route and concise reason. `BYPASS_ROUTER` retains an
   already-feasible operator baseline; it never means bypassing hard policy.
   Use `aeep inspect DECISION_ID` only when detailed constraints, candidates,
   or scores are needed.

5. Execute only when the selected route and side effect are appropriate:

```bash
python -m aeep run CAPABILITY --input '@input.json' --agent --compact
```

6. Never add `--approve write`, `destructive`, `financial`, or `--approve-unsafe-executor` unless the user/operator explicitly approved the action and the manifest policy also allows it. A model tool call never counts as that approval.

7. For constrained hardware, pass current context. For persistent host pressure, report the named resource separately with `aeep quota observe`:

```bash
python -m aeep route CAPABILITY \
  --input '@input.json' \
  --policy resource_saver \
  --context '{"compute":{"context_tokens_remaining":4000,"available_memory_mb":1024}}' \
  --compact
```

8. When AEEP selects a `host` or `delegate` route, follow its instructions using the named subscription/browser/computer-use/model resource. Then report actual outcome and subscription use:

```bash
python -m aeep record DECISION_ID EXECUTOR_ID success \
  --resources '{"latency_ms":1200,"input_tokens":800,"output_tokens":100,"context_tokens":1600}' \
  --quota-state normal \
  --output-valid \
  --compact
```

After an official throttle or reset signal:

```bash
python -m aeep quota observe RESOURCE_ID tight --source rate_limit --compact
```

Report failures and timeouts too; otherwise future routing remains biased by static priors. Report only the selected delegated executor and submit one final outcome for that decision/executor pair. Use `ActionProfiler` rather than fabricating a delegate report for unrelated work.

9. Use route calibration only after explicit operator confirmation because it executes several alternatives and may incur charges or disclose input to multiple providers:

```bash
python -m aeep benchmark CAPABILITY \
  --input '@input.json' \
  --confirm-all-routes \
  --compact
```

Never benchmark non-idempotent, destructive, financial, or sensitive actions autonomously. To force one already-reviewed route instead, use `--executor-id EXECUTOR_ID`.

## Output handling

- Commands emit JSON on stdout.
- Exit `3` means no feasible route; read rejection reasons rather than bypassing constraints.
- Exit `4` means attempts completed but no valid success.
- Do not scrape human prose or infer approval from a low score.
- Do not treat estimated tokens as exact provider billing usage.

## Plain tool-call bridge

When an agent framework returns one of the AEEP function calls but has no MCP client:

```bash
python -m aeep tool-call aeep_execute_action --arguments '@call.json' --compact
```
