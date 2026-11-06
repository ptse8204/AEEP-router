# Langfuse repeat with a fixed private Redis address

The approved correction kept Redis on the owned internal network
and gave the Langfuse processes a fixed host mapping. The [stopped
diagnosis](stopped-web-diagnostic.json) confirms the mapping was
applied and the web log reached Next.js readiness. Host health still
failed on all 20 probes. The bounded logs contained connection
timeouts. Trace ingestion and disablement are open.

The [canonical result](service-execution/summary.json) records 142
total operations, including 33 more for this attempt, zero model
turns and $0 cash. All charges settled and all owned resources were
stopped and retained. Before another full service repeat, isolate
private service-to-service connectivity from Docker's host loopback
forwarding. Preserve the exact failed run.
