# SkillsBench ordinary CLI preparation

The [workflow](workflow.json) selects one previously verified reference task per
domain. Both use the managed evaluator and the original task-only SkillsBench
pack. The existing format-json candidate is a preview fixture. A composed run
needs a reviewed, task-relevant candidate and controlled worker binding.

From the repository root, inspect either configuration through the ordinary CLI.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m aeep_toolkit workflow plan \
  --workflow reports/toolkit-v2/c13/skillsbench-ordinary-cli-preparation-20261105/workflow.json \
  --configuration document-data
```

Use `software-engineering` for Spring Boot. The [preview results](preview-results.json)
bind the two configurations to their protected reference summaries. Both
separate public agent inputs from the protected verifier and oracle. Canonical
preparation rejected both incomplete definitions without writing a plan. The
first audit expected the internal rejection text. The CLI returns a sanitized
message, and the in-process check confirmed the underlying preparation guard.

| Configuration | Reference task | Observed protected grader command |
| --- | --- | --- |
| Document/data | Sales Pivot | 1.73 seconds |
| Software engineering | Spring Boot/Jakarta | 42.97 seconds |

These are complete command intervals from the prior protected reference
receipts. The executable recipe currently allows a command deadline of at most
30 seconds. The measured Spring run exceeds that bound. Establish a compatible
protected grader path with the original assertions and a reviewed workload
deadline before attempting canonical execution. The timing is an observed
engineering interval for one run.

Next bind the exact asset-use determinations, protected grader recipe, setup
request and worker evidence. Local reference evidence supplies no provider
disclosure authority. Keep the current fail-closed checks and leave comparisons
paused. Both ordinary CLI execution journeys remain open.
