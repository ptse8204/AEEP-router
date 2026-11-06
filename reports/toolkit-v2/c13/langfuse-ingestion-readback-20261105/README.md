# Private Langfuse receipt ingestion and disablement

The [readback](service-execution/summary.json) found the exact trace,
span and canonical receipt hash on the second observations request.
That request returned HTTP 200. The first readback timed out. The
retained web and worker both resolved the reviewed Redis address and
returned an authenticated PING.

| Check | Evidence |
| --- | --- |
| Trace linkage | Trace `1b8279e1c58c0bdd4119dd8eb2690108`, span `51c2f243db720330`, receipt SHA-256 `1b8279e1c58c0bdd4119dd8eb269010851c2f243db720330958e9b7165d99b00` |
| Export disablement | The ordinary CLI returned disabled in a deny-all network sandbox. No second transport operation was reserved. [Disablement](../langfuse-disablement-20261105/service-execution/summary.json) |
| Resource ownership | The six services were stopped. Both initialization containers, all images and all volumes were retained. [Stop record](service-execution/stop-verdict.json) |
| Accounting | The Langfuse grant settled at 203 operations and 466.83 measured seconds, with zero model turns and zero cash authority. There is exactly one POST reservation. |

The [first approved carrier run](../langfuse-loopback-carrier-20261105/service-execution/summary.json)
reached web and worker startup, then stopped at the inherited mount
check. Docker Desktop had prefixed the exact ClickHouse path with
`/host_mnt`. The [corrected guard](../langfuse-retained-mount-20261105/preflight.json)
checked both mount observations and rejected seven altered cases.
The first continuation then stopped before reservation on a stale
budget predecessor. The [prestart record](../langfuse-retained-budget-20261105/prestart-correction.json)
binds the canonical predecessor under the standing delegation.

The [sole POST](../langfuse-retained-budget-20261105/service-execution/summary.json)
was forwarded but its transport acceptance was unverified. The
original failure receipt stays terminal. The readback establishes
ingestion independently, without replaying that request or changing
its result. The [separate Redis path probe](../langfuse-redis-path-20261105/result.json)
returned all five authenticated PINGs. Its [cleanup recovery](../langfuse-redis-path-20261105/cleanup-recovery.json)
removed the empty owned network and retained the original unmeasured
cleanup reservation under the probe's separate grant.

This evidence applies to the private Langfuse 4.55.0 deployment and
the retained installed AEEP exporter pinned in the
[exact review](operation-review.json). Full stack readiness, composed
workload telemetry and comparative acceptance remain open.
