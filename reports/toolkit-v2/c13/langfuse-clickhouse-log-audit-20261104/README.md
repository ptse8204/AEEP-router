# ClickHouse failed while allocating its background scheduler

The first read-only file audit passed under review 3ea451d3. Docker copied three
fixed paths from the stopped owned ClickHouse container into a bounded transient
reader. No guest program ran, and no raw file was written to the reports.

Both retained server logs contain fatal scheduler/global-thread-pool diagnostics
requesting 512 threads. The container had a 256-PID cap. The normal log also
contains error code 198. This is the observed startup incompatibility. Numeric
values found in the raw config.xml include comments; they do not prove effective
server settings. The raw configuration and local task keys remain private.

The audit added two settled operations to the existing grant. The proposed
configuration correction still requires an actual service attempt and exact
trace/span/receipt-hash ingestion check. It does not establish production sizing.
