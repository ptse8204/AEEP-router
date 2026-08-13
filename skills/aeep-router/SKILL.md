---
name: aeep-router
description: Profile, compare, and safely execute equivalent agent actions across local Python, CLI, HTTP, MCP, and browser/computer-use routes using AEEP. Use before an expensive or repeated tool action, when context/compute/budget is constrained, or when choosing among multiple execution surfaces.
allowed-tools: Bash(python -m aeep:*), Bash(aeep:*)
---

# AEEP action router

Use AEEP at the bounded-action level. Do not send an open-ended objective such as "plan a vacation" as one capability. Decompose it into registered capabilities first.

## Workflow

1. Discover available capabilities when uncertain:

```bash
python -m aeep list --compact
```

2. Route before executing when the task is expensive, risky, novel, or has several alternatives:

```bash
python -m aeep route CAPABILITY --input '@input.json' --compact
```

3. Inspect `selected_executor_id`, all `rejection_reasons`, estimates, and score components.

4. Execute only when the selected route and side effect are appropriate:

```bash
python -m aeep run CAPABILITY --input '@input.json' --compact
```

5. Never add `--approve write`, `destructive`, `financial`, or `--approve-unsafe-executor` unless the user/operator explicitly approved the action and the manifest policy also allows it. A model tool call never counts as that approval.

6. For low quota or constrained hardware, pass current context:

```bash
python -m aeep route CAPABILITY \
  --input '@input.json' \
  --policy resource_saver \
  --context '{"compute":{"context_tokens_remaining":4000,"available_memory_mb":1024}}' \
  --compact
```

7. When AEEP selects a `delegate` route, follow its instructions using the host's browser/computer-use/model tools. Then report actual outcome:

```bash
python -m aeep record DECISION_ID EXECUTOR_ID success \
  --resources '{"latency_ms":1200,"input_tokens":800,"output_tokens":100,"context_tokens":1600}' \
  --output-valid \
  --compact
```

Report failures and timeouts too; otherwise future routing remains biased by static priors. Report only the selected delegated executor and submit one final outcome for that decision/executor pair. Use `ActionProfiler` rather than fabricating a delegate report for unrelated work.

8. Use route calibration only after explicit operator confirmation because it executes several alternatives and may incur charges or disclose input to multiple providers:

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
