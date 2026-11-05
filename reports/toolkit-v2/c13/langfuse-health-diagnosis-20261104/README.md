# Retained datastore health observations

The first read-only diagnostic passed under review 9923284a. It checked the five
stopped owned containers and filtered their bounded startup logs in memory.
The report contains states, exit/OOM/health codes, hashes and fixed categories.
It contains no raw log or key values. No service or guest executable ran.

ClickHouse health probes returned connection refused. The other three datastore
health logs contain successful exit-zero probes; their post-stop health status
must not be treated as proof that all four failed startup. ClickHouse's detailed
file logs were then inspected separately under their own first-attempt review.
All diagnostic costs stay in the original service grant. Neither pipeline
restarted a container or supplied benchmark/usefulness evidence.
