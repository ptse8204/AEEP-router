# Langfuse repeat after macOS sandbox update

The earlier approved heap review stopped before dispatch because macOS
changed the `sandbox-exec` fingerprint. The [new preflight](sandbox-preflight.json)
verified Apple's signature and five unchanged permission checks. The
operator approved the replacement review.

The [service result](service-execution/summary.json) shows that the
datastores and web container started, then all 20 host health probes
failed. The stopped web logs showed repeated Redis name-resolution
errors. All 33 additional operations settled, bringing the grant to
109 operations. The driver stopped and retained the owned containers.
Worker startup, trace export and ingestion remained unstarted.
