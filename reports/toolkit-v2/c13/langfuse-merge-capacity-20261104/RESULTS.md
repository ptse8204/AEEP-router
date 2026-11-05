# Langfuse passed datastore startup and reached web initialization

The 16-thread merge setting cleared ClickHouse readiness. PostgreSQL, Redis,
Minio and bucket setup also completed. The web container started, but the
health loop received no successful result before cleanup. The retained web
container log reports migrations applied and Next.js ready, followed by a
V8 heap exhaustion at the 640 MiB old-space limit. The process exited 134,
with Docker OOMKilled false.

All seven owned containers stopped. The [terminal result](service-execution/summary.json)
settled at 76 operations, zero model turns and 179.64111808408052 seconds.
The worker, receipt export, ingestion and disabled export checks remain
unstarted. Existing images and all previous namespaces remain intact.
