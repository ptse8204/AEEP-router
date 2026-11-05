# Compose passed; ClickHouse startup needs a smaller background pool

The approved correction passed Compose validation and created five owned
containers: the Minio ownership initializer and four datastores. PostgreSQL,
Redis and Minio health logs contain successful probes. ClickHouse never opened
its HTTP endpoint. Its retained logs report a fatal background scheduler/global
thread-pool failure requesting 512 threads under the configured 256-PID cap.
OOMKilled was false; exit 137 alone does not establish a memory failure.

No web/worker, receipt export or ingestion check ran. Cleanup verified and
stopped the five owned containers, retaining their volumes, network and images.
The service grant settled at 23 cumulative operations and
63.607842459343374 seconds, including the 13 previous charges.

Two first read-only diagnostic pipelines then inspected retained health metadata
and three ClickHouse files. They ran no guest program and retained only hashes,
fixed error categories, numeric error/thread counts and selected public pool
settings. Raw files, logs and task-local keys were not retained in reports. The
same grant now has 31 operations / zero models / 64.60480687581003 seconds, with
no outstanding reservations. Preparation outside the measured operations is
NOT_RECORDED; CPU, memory, wire bytes and cash measurements remain unknown.

The proposed threadpool correction keeps the PID cap and images, adds a readonly
small-workload configuration fragment, and creates a separate owned namespace.
The stopped attempt stays intact. Startup and exact receipt ingestion remain
unverified; the proposed settings do not close production resource acceptance.
