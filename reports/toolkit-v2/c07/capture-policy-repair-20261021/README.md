# Preserve policy overrides in the metrics launch

Both approved collector image builds completed. Both sandboxed collector endpoint
checks returned permission denial. The subsequent canonical pair conformance
failed configuration checks: required disabled features were not observed, and
treatment candidate inventory was inconsistent. Both workers were cleaned up and
the proxy was restored stopped. Zero model turns ran. The actual predecessor
records are retained in `predecessor-records.json`.

The relay placed the pinned policy overrides before the app-server subcommand and
its own telemetry overrides after it. The correction keeps both sets in the same
CLI scope, with telemetry overrides last in that scope. Two synthetic subprocess
regression cases fail on the old ordering and pass after the change. They check
policy retention and that earlier settings cannot reenable prompt logging or
change the selected telemetry exporter. The focused suite passed117 tests.
These are first-party synthetic results. The exact installed Codex parser and
prospective conformance have not yet verified this hypothesis or correction.

No dependency, protocol schema, evidence threshold, model or destination changes.
The collector source changed, so the old package and live reviews remain
historical. A single required integrated verification cycle is now pending for
this source. The changed collector must get its own exact execution review after
that cycle, together with the current wheel check. Do not replay either terminal
repair driver or start model diagnostics before all boundary checks pass.
