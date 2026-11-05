# Fit the one-receipt Langfuse check within its existing PID cap

The approved tmpfs correction passed Compose validation and started the four
datastores. ClickHouse never became ready. Read-only inspection of its retained
logs found a fatal background scheduler/global-thread-pool failure requesting
512 threads; the container was capped at 256 PIDs. PostgreSQL,Redis and Minio
health logs contain successful probes. Cleanup stopped only the five verified
owned containers. All old containers,volumes,keys,images and receipts remain.

This proposal configures 16 scheduler threads,three auxiliary pools of four,and
an eight-thread background pool for the single minimized receipt workload. The
256-PID cap,images,memory/network/security settings and software versions stay.
A new readonly XML fragment uses ClickHouse's existing config.d mechanism. These
are proposed engineering settings; startup/ingestion is still unverified and
production resource qualification remains separate.

A new owned namespace avoids replacing or deleting the stopped attempt's state.
It creates at most eight containers,five volumes and one internal network,using
the same private task-local keys. Only 127.0.0.1:39067 is published. All old
resources remain. No model,download,build,install,new provider or credential
access is included. Waza sign-in stays deferred.

The same canonical receipt export,exact trace/span/hash readback and disabled
export checks remain. One attempt,at most 63 additional operations in the
existing 3,200-second/zero-model/$0 ceiling. The finite operation amendment keeps
all 31 charges and raises the cumulative cap to 94. No successful OCI,source,
wheel,docs,ToolHive build/info/audit or diagnostic check is replayed.

[ClickHouse configuration fragments](https://clickhouse.com/docs/concepts/features/configuration/server-config/configuration-files)
and [scheduler settings](https://clickhouse.com/docs/reference/settings/server-settings/settings/background-schedule)
are the primary configuration references. New static checks establish only the
intended adaptation. The real service attempt requires this exact repeat approval.
