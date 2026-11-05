# MCP lifecycle stopped before image creation

The exact first-attempt review `9bad9397` was executed under the standing pipeline
authority. Parent identity and owned-name collision checks passed. The COPY-only
image build failed because the private Docker configuration selected the legacy
builder, which rejects `COPY --chmod`. The public error is in failure-build.json.

Read-only post-failure inspection found no owned output image, container, network
or volume. No ToolHive controller, host-profile probe, MCP server or MCP client
was executed. Five operations and 0.5746463751420379 seconds are settled in the
existing ledger, with zero model turns and no outstanding reservations. Other
measurements remain unknown. The original context and all prior work remain.

The separate packaging correction uses ordinary COPY with the unchanged owned
source set to mode 0444. It preserves the old charges and runs only the remaining
build/lifecycle work after exact repeat approval. No dependency, BuildKit plugin,
source package, software version, permission or server behavior changes. Waza
sign-in remains deferred and is unnecessary for these checks.

The operator pipeline and first-party interval/formatter preparation controls
are implemented. Actual ToolHive MCP integration remains unproven. This work
cannot close the stack, benchmark-reference, usefulness, resource or release gates.
