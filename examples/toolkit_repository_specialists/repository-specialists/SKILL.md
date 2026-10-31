---
name: repository-specialists
description: Choose optional Ruff lint fixes and LibCST object migrations for Python maintenance tasks needing either or both operations.
---

This reviewed worker provides Ruff 0.16.2 at `/opt/aeep-specialists/bin/ruff` and
LibCST 1.8.6 under `/opt/aeep-specialists`. Use either, both or ordinary tools
according to the current task.

For requested lint cleanup, use explicit editable paths and relevant Ruff rule
codes with `--isolated --no-cache --no-unsafe-fixes`. Inspect findings before `--fix`.
For an object/import migration, use LibCST's `parse_module`, `CodemodContext` and
`RenameCommand` API with exact qualified names and a fresh command for each file.
Parse source without importing repository modules or project-provided codemods.

Inspect the combined diff for task scope, preserved behavior, comments and strings.
Do not perform unrelated lint cleanup during a migration. Neither tool's success
is an independent correctness verdict. Do not install software, change unlisted
files or contact external services. Leave both specialists unused when irrelevant.
