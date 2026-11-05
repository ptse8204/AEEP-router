# Langfuse stopped datastore diagnosis

The approved [service attempt](../langfuse-threadpool-correction-20261104/service-execution/summary.json)
ended at datastore readiness. All five new owned containers stopped, with
accounting settled and no receipt export. PostgreSQL, Redis and Minio had five
successful health probes each. ClickHouse had five failed probes.

My reviewed diagnostic assumed the completed one-shot container had a Docker
health field. The template failed before reading logs. Its two operations
remain charged. The narrow read-only follow-up inspected owned IDs and filtered
their state and retained ClickHouse files in memory. It retained
[health and mount metadata](retained-metadata.json) and
[startup constraint facts](stopped-clickhouse-constraints.json). Those follow-up
reads have no separate metering. Raw logs, configuration and keys stayed private.

The 16/4-thread scheduling pools initialized. ClickHouse reported that the
mutation threshold of 20 exceeded the merge pool's 16 logical slots. That is
the new startup blocker after correcting the original 512-thread request.
