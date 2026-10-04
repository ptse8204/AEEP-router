# Offline outer-worker timeout probe

The bounded synthetic probe passed all eight cases in 0.283 seconds on 2026-10-04. The verification source digest matched the frozen digest before and after the run. The exact case definitions are in [test-definition-review.json](test-definition-review.json), with machine-readable results and definition/script hashes in [outcomes.json](outcomes.json); the retained harness is [probe_outer_worker.py](probe_outer_worker.py).

Returning `RawExecution(TIMEOUT)` from the inner adapter skips artifact retrieval, closes the transport, completes worker cleanup, and returns the original `TIMEOUT` error type and metadata. A successful artifact replaces the inner output and records its digest and size. An artifact `ConfigurationError` becomes `FAILED / WORKER_ARTIFACT_FAILED`, while cleanup still runs. Delaying cleanup by 0.05 seconds delays the return by about 0.052 seconds.

Cancellation during artifact retrieval or cleanup propagates `CancelledError`; because no `RawExecution` returns, no raw metadata is available from those cases. Through the actual `ManagedHostExecutor` start/handle path, an outer deadline whose synthetic inner coroutine catches cancellation and returns `RawExecution(TIMEOUT)` returns that timeout after cleanup. A deadline during pending artifact retrieval instead raises `TimeoutError` after cancellation and cleanup, with no returned raw result.

The fixed `host_progress` value is only a synthetic marker used to test metadata preservation. Its `turn_completed` text is not an observation of a real turn and carries no semantic claim about the timeout scenarios. These results characterize synthetic current-code behavior; they do not reconstruct or explain historical timeout trials.
