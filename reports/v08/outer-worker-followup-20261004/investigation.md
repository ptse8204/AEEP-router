# Outer worker timeout investigation

The five recorded workbook timeouts point to the adapter’s turn-execution
timeout/cancellation path, before outer output retrieval. This is an inference
from the saved receipts and the exact historical code. It narrows the failing
stage; it does not explain why the host turn exhausted its time.

## Evidence

- Each trial completed with a real saved `TIMEOUT` receipt. The benchmark keeps
  receipts read back from the router; an uncaught invocation exception follows
  a different path and leaves the trial failed.
- All five receipts lack `output_schema_bytes`, `result_bytes`,
  `thread_identity_digest`, `turn_identity_digest` and `host_runtime_digest`.
  Those fields are present in the passing holdout-73 comparison. Their absence
  matches the partial-execution return, rather than the normal terminal-result
  return. The generic saved error label alone cannot establish this distinction.
- The historical wrapper retrieves its output artifact only after a successful
  inner execution. A returned timeout skips that retrieval. Cleanup failure
  changes the returned status to `FAILED`, so the preserved timeout status also
  implies successful worker cleanup in this path.
- The callback itself completed, followed by further host action and usage
  events. These are opaque events without timestamps or item types. They do not
  reveal whether later activity was reasoning, commands or final-answer work.

The [historical source comparison](historical-source-comparison.json) verifies
its wheel against the SHA-256 recorded in the October 3 build report. The worker
wrapper and transport shutdown methods match today’s code. The managed-host
executor, worker transfer code, benchmark runner, execution journal and container
cleanup implementation are byte-identical. The router’s only change since that
package is the new progress-metadata allowlist entry.

The [receipt-field audit](historical-timeout-phase-diagnostic.json) retains the
five timeout rows and the passing comparison, with the exact fields inspected.
Eight [bounded synthetic probes](outcomes.json) passed in 0.283 seconds under
Luna/xhigh review. They exercised the current wrapper and the actual
`ManagedHostExecutor` start/handle deadline path with fake inner execution,
transport and worker objects. They confirmed the different return and exception
paths. The [run history](synthetic-run-history.json) records an initial successful
run and one report/assertion correction followed by a successful rerun; these
are the same eight synthetic cases, not independent evidence. These probes ran no model, Codex process, container or network operation;
they do not reproduce the historical live workload.

## What remains unknown

The records do not identify which timeout or cancellation source fired, whether
the callback reply reached the host, or the last host activity before the cutoff.
They do not provide separate artifact or cleanup timings. Receipt duration minus
reported execution latency includes different work and has a similar gap in the
passing comparison; it cannot be assigned to cleanup.

The current progress summary is captured before interruption and can help a
future diagnostic distinguish a running callback, a locally written reply,
continued host activity, an output message and a terminal notification. Its flags
do not establish task success or peer acknowledgement. Artifact retrieval and
cleanup remain outside that summary.

Cancellation during those later stages can prevent a result from returning.
That is a separate observation gap, not an explanation for these five returned
timeout receipts. No change to deadlines, retry behavior, model settings or
qualification thresholds follows from this investigation.

## Next diagnostic

Use fresh, separately reviewed diagnostic cases after the changed adapter has
fresh applicable conformance. Keep Luna/xhigh and the intended workflow fixed,
then inspect the saved progress summary at a failure:

| Observation | What to investigate next |
|---|---|
| Callback started but has not returned | Callback execution or transfer inside the callback |
| Handler returned but no local response write completed | Transport response writing |
| Reply written and later host events continue | Host work after the tool result |
| Output message received without a terminal notification | Turn-completion signaling |
| Turn completed but no outer result returned | Output retrieval or shutdown, with separate stage instrumentation |

These are diagnostic distinctions, not retrospective proof. Do not replay the
failed holdouts as fresh evidence or change their recorded outcomes. Any new
live diagnostic must retain its costs in the existing assessment ledger.

## Storage and validation scope

This follow-up uses read-only database queries, in-memory package inspection and
small synthetic probes. It creates no images, containers, volumes, dependency
installs or database copies. Production source and the historical verification
lock remain unchanged. The previous full software validation still describes
this source; the synthetic probes do not supply new live conformance.
