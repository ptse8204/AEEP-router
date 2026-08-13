# Agent instructions for this repository

## Goal

Maintain a secure, provider-neutral action economics profiler/router. Do not turn AEEP into a model-specific wrapper or speculative token system.

## Required checks

After code changes:

```bash
python -m compileall -q src examples tests
PYTHONPATH=src python scripts/generate_schemas.py --check
pytest
coverage run -m pytest
coverage report -m
```

## Invariants

- Hard constraints are evaluated before scores.
- Requests cannot weaken manifest policy guardrails.
- `command` uses argv only; never introduce shell interpolation.
- Non-idempotent fallback is off by default.
- Raw resource dimensions remain in receipts.
- Provider claims are not observations.
- Action payloads and output data are not persisted by default.
- Model-facing tool arguments cannot raise operator approval ceilings.
- Benchmarking is not exposed as an unrestricted model tool.
- MCP stdout contains protocol JSON only.
- Modern MCP request metadata/header mirrors fail closed; legacy compatibility remains tested.
- External outcome reports apply only to the selected delegate, are terminal, and are stored once atomically.
- Resource measurements must be finite and non-negative.
- Tool behavior is shared across MCP, CLI, and provider-schema exports.

Read `SPEC.md`, `ARCHITECTURE.md`, and `SECURITY.md` before changing protocol or executor behavior.
