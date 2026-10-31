---
name: ruff-safe-fixes
description: Apply selected safe Ruff fixes for requested Python lint cleanup while preserving unrelated code and behavior.
---

Ruff 0.16.2 is available at `/opt/aeep-specialists/bin/ruff` in this reviewed
worker configuration. Use it when its rules address the current task. Ordinary
editing tools remain available.

Pass explicit editable paths and task-relevant rule codes. Use `--isolated`,
`--no-cache` and `--no-unsafe-fixes` to avoid project configuration and unsafe fixes.
Inspect findings before applying `--fix`; check the resulting diff for scope and
preservation. Ruff's safe-fix label is not an independent correctness verdict.

Do not install packages, change the rule set to satisfy a hidden test, edit
unlisted files or contact external services. If the task does not need lint
cleanup, use the ordinary tools.
