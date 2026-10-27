# Collection diagnostics completed — causes remain unresolved

Approved `faa10772` completed all four calls once. The collector did not identify
an exact cause for any case. This is a retained limitation, not a successful repair.

| Reference | Captured diagnostic | What remains unknown |
| --- | --- | --- |
| MCP222 | Exit2; no recognized error category | Exception class and cause |
| MCP384 | Exit2; no recognized error category | Exception class and cause |
| Twyn317 | Exit2; `ModuleNotFoundError`, one identifier filtered out | Missing module and dependency cause |
| CanvasAPI716 | Exit2; `ModuleNotFoundError`, one identifier filtered out | Missing module and dependency cause |

The allowlists and finite category parser were too restrictive for these failures.
No raw log or traceback was retained; the missing names cannot be recovered from
these receipts. Static source inspection cannot establish their exact runtime
cause. No speculative dependency installation or automatic replay follows.
These four tasks remain excluded from the current pool. Curation will proceed
with other sources before spending more calls on these incompatibilities.

[The canonical audit](completion-audit.json) reopened four physical receipts and
completed attempts. All six operations completed, charging11.11573583446443
operation-seconds, no model turns and no cash. Owned containers are absent;
both images remain, and no host canary was created. The grant is13140 operations,
3755 turns,119727.43407934532 seconds and0.0 cash. All earlier failures, charges
and the42-case pool are unchanged. No qualification, usefulness, selection or
resource acceptance gate closes. Product source remains `4cb0bf74`.
