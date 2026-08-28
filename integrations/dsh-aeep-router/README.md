# AEEP host-native router for DeepSeek Harness

This Cordis plugin routes before a model sees a tool catalog. A human or host
submits one exact action through DSH's native command registry:

```text
/aeep {"capability":"web.page.read@1","input":{"url":"https://example.com/"},"prompt":"Return the page title."}
```

The command preflights the action through AEEP, queues only `prompt`, and keeps
the capability/input hint transient. The next model request contains the one
operator-mapped canonical tool plus `baselineTools` (empty by default). Selected
implementation tools remain hidden and a DSH guard denies model-direct calls
outside that allowlist.

One argv-only `aeep host-bridge` child remains alive for the plugin lifetime.
JSONL messages and responses are bounded; a failed request is not retried. A
later request may start a fresh bridge. AEEP receives resource counts, exact
rendered-result pressure, decision/executor IDs, and bounded receipt links—never
prompts, arguments, tool values, outputs, or session IDs.

The pre-enable local transport check used ten identical fixture routes on the
macOS test host. Median round-trip time was 368.90 ms for process-per-event and
2.33 ms for the persistent bridge; the bridge spawned one Python child. Tests
also compare route/receipt semantics across the direct Router and bridge paths.
These transport numbers are not provider-token or application-latency claims.

Every source and target parameter/output schema needs a reviewed digest. Without
`resultAdapter`, source and target output digests must be identical. The only
adapter is `read-url-to-web-fetch-v1`; it requires a true status code, final URL,
text, truncation state, and content type. The currently tested `dsh-read-url`
version lacks true status and must remain absent from executor mappings.

The AEEP manifest defines corresponding `host` executors. Discovery never
creates mappings, and the plugin never installs, qualifies, activates, or raises
approval. On macOS, an x86 DSH/Node process may need an ARM Python argv prefix:

```yaml
aeepCommand: /usr/bin/arch
aeepArgs: [-arm64, /absolute/path/to/python3, -m, aeep]
```

Run offline checks with:

```bash
node --test test.mjs
```

Installation and live provider-token campaigns remain separate operator actions.
