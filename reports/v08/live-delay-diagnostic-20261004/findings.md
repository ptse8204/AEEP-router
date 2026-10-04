# Live outer-worker delay investigation — October 4

This investigation uses source `e6b71acb…`, which passed the [October 4 software checks](../outer-worker-delay-20261004/validation-terminal.json). It renews the worker boundaries before making a small live diagnostic. It does not rerun historical holdouts or qualify a candidate.

## Environment checks

All 22 worker checks and three native boundary/cancellation checks passed. The selected worker reported available capacity. The workers remained isolated, the native manifest and container images were unchanged, and the proxy returned to its original stopped state after each completed stage. The [worker audit](c-worker-components-terminal-audit.json), [native result](native-components-treatment-result.json) and [capacity result](c-treatment-capacity-result.json) retain the measurements and their limits.

The diagnostic implementation changed three source-derived callback identities: the callback implementation, native executor fingerprint and native backend digest. The [renewal record](worker-renewal-proposal.json) checks that the remaining callback fields, permissions, images, skills and instructions match the historical configuration. Earlier evidence remains attached to its original source.

## First diagnostic: rejected helper result, followed by a timeout

The first fresh workbook contained fractional prices. It passed the JSON input schema, but the native workbook validator supports bounded integers and rejected the input before comparing the output. This was a diagnostic-preparation error. The native process completed and returned schema-valid output; its receipt has `task_valid: false`. The [input-domain audit](first-input-domain-audit.json) records this distinction.

| Observation | Seconds from adapter start |
|---|---:|
| Callback requested | 14.725 |
| Handler completed | 16.043 |
| Response written to the local pipe | 16.043 |
| Last observed event: a reasoning-item start | 198.465 |
| Progress snapshot before interruption | 199.071 |

Neither a final answer nor a turn-completion event was observed at the snapshot. The final-answer flag also accepts legacy unphased messages; the turn-completion flag covers terminal events, including failed or interrupted turns. The complete diagnostic operation took 203.231 seconds and returned a timeout. The host continued emitting events after the helper response; the event contents were not retained. A local pipe write does not prove that the host processed the response.

The [phase analysis](phase-analysis.json), [independent Luna/xhigh audit](first-run-phase-audit.json) and [original result](diagnostic-result.json) retain those facts. This may be a failed-helper recovery path. It does **not** reproduce the five historical timeouts whose child receipts were task-valid, and it does not explain those historical failures.

The current wrapper skips final artifact retrieval when the inner result is a timeout. Worker cleanup and proxy shutdown succeeded. Retrieval and cleanup durations were not measured separately. Thus this case narrows the delay to the host completion/recovery phase, without identifying what the host was trying to do.

## Second diagnostic: valid helper and normal completion

A new three-row integer-only workbook passed the native input-domain check before execution. It used a fresh request and one-attempt scope, the same Luna/xhigh worker, and the same permissions and time limits. It did not replay the first request or a historical holdout.

The [successor result](diagnostic-v2-result.json) passed in **23.510 seconds**. Its callback response was written at **16.593 seconds**, and the host reported normal turn completion at **19.319 seconds**: **2.727 seconds after the response write**. A final answer was observed. Both the native child and outer receipt were task-valid. The worker returned a 5,534-byte workbook artifact, and worker cleanup and proxy shutdown succeeded. The [phase audit](phase-analysis-v2.json) links the exact receipts, artifact digest and progress markers.

This establishes that the current valid-callback path can finish normally, including artifact retrieval. It does not establish broad reliability, an independent campaign grade, a speed benefit or the cause of the five historical timeouts. A separate controlled study would be needed to compare behavior or change qualification status.

The next investigation should focus on the period after a **task-valid** callback response. Keep those cases separate from failed-helper recovery. A bounded content-free event timeline would help distinguish repeated tool work from waiting; final artifact retrieval and cleanup still need their own duration measurements before attributing overhead to either stage. No production timeout or completion rule was changed from these two cases.

## Report recovery

A separate report-helper error occurred after the receipt and operation cost were saved: the dynamically imported result model could not resolve the `Any` type annotation. The [offline reproduction](diagnostic-recovery-reproduction.json) verified that registering the same frozen module resolved its namespace. The [reviewed recovery](diagnostic-result-recovery-result.json) inserted the original failed summary into its missing canonical record, without changing its contents, grant counters, measurements, reviews or probe count. No model call was repeated to repair reporting.

## Scope and costs

The first diagnostic and its prerequisites used 14 operations, one model turn and 252.543 measured operation-seconds. These are ledger operation lifetimes counted once; child measurements are not added again. Report preparation and audit overhead, cash and complete whole-system resource costs remain unknown. The [first terminal resource audit](resources-audit-final.json) records exact image identities, charges and the two unrelated historical reservations that remain untouched.

The [finite successor amendment](finite-diagnostic-amendment-v2.json) allows one additional fresh integer-only case, with its own request and task scope, after input-domain validation. It preserves the first failure and all its costs. Across both diagnostics the ceiling is 18 operations, two model turns, 1,596 reserved seconds and no cash spending.


The final [resource audit](resources-audit-v2-final.json) finds **18 settled operations, two model turns and 282.884 measured operation-seconds** across prerequisites and both diagnostics. Both unrelated historical reservations remain unchanged. There are no running containers, no new image builds or pulls, and no user resources were deleted. The retained outer evidence databases total about **337 MiB**, with about **6.1 MiB** of report files at the final storage check. **143.5 GiB** remained free, above the 50 GiB reserve. Exact paths, bytes, source and verification-lock hashes are in the [completion record](completion-summary.json).
