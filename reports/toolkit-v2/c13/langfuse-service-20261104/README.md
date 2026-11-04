# Private receipt ingestion check

This check connects the installed ordinary CLI to an actual local Langfuse
deployment. A successful result must match the source receipt hash, trace ID and
span ID through the upstream observations API, then prove that disabled export
does not create another transport operation. HTTP acceptance alone cannot pass.

The source receipt comes from the completed SkillRank catalog journey. That
journey used authored catalog entries and the real SkillRank server. Exporting
its receipt adds no task trial, candidate benefit or selection evidence.

The prepared workflow keeps both document/data and software configurations.
Only telemetry runs here: it does not execute or qualify their SkillsBench tasks.
The generic v1 HTTPS-only setup preview cannot express this local HTTP service;
the registry records that limitation. The exact receipt-export and service
definitions supply the separate authority. General service setup readiness stays
open until that workflow limitation is resolved.

## Exact scope

- Reuse six acquired immutable ARM64 images and the verified installed runtime.
  No pull, build, package installation or source-suite replay.
- Use upstream Compose through the fingerprinted existing plugin. Create eight
  owned containers, five new data volumes and one internal network. Two containers
  perform one-time volume ownership and bucket initialization.
- Publish only web/OTLP at `127.0.0.1:39067`. Generate keys solely for this new
  local project after approval. Keep them in a private mode-0600 Compose/config
  workspace. No provider, operator, GitHub or Codex credentials are read.
- Keep root filesystems read-only except ClickHouse's new container layer, where
  its nonroot upstream entrypoint creates user configuration. Postgres/Redis may
  use only their reviewed bootstrap capabilities. No privileged mode, host PID
  namespace, Docker socket, unrelated volume or home directory is mounted.
- Run one fixed external-connect denial probe without an application payload.
  If it connects, stop before exporting anything. This is a service-network
  check, not qualification of an agent or MCP worker.
- Export one minimized receipt. At most twenty health observations and eight
  ingestion observations may poll this local service. No prompt, artifact
  contents, model trace, expected answer or provider credential is exported.
- Check disabled export from the other named configuration with no auth variable.
  It must create no new transport operation.
- Stop only containers whose labels, immutable image and IDs match this project.
  Retain containers, images, volumes, network, local keys and installed runtime
  for reuse. No old resource or backup is deleted.

The proposed 4 GiB aggregate service memory cap is for this single receipt
engineering journey on the existing Docker VM. It is not a production budget or
resource-acceptance threshold. Actual memory, CPU and cash measurements remain
unknown unless separately observed. Keep at least 50 GiB usable host space.

The new isolated grant permits at most 63 operations, zero model turns and
3,200 reserved seconds, with zero cash authority. This is a conservative ceiling,
not an expected duration. Existing counters remain intact. Command wrappers
exclude nested canonical CLI intervals, and cleanup has a reservation made before
startup. Interrupted or indeterminate work cannot replay automatically.

## Execution after exact approval

Read and hash `operation-review.json`. Record the actual operator approval in
`operator-approval.json`; an example or prepared file is not approval. Then run:

```sh
python3 reports/toolkit-v2/c13/langfuse-service-20261104/run-docs.py --execute-approved REVIEW_SHA256
python3 reports/toolkit-v2/c13/langfuse-service-20261104/run-service.py --execute-approved REVIEW_SHA256
```

These are independent components. A settled docs failure does not authorize a
repair/retry or block the service component. Service accounting or cleanup
uncertainty stops dependent dispatch. Inspect started files and canonical ledgers
before any resumption. The driver never resets allowances, regenerates an
existing private Compose file or adopts an existing project resource.

The current offline docs check covers 72 exact inputs with unchanged cached
markdownlint and Lychee tools. It includes the six corrected duplicate blank
lines from the failed preceding attempt. No successful wheel/image/source check
is repeated. Both checked versions and the failed attempt remain preserved.

Preparation controls use first-party substitutes and a standard-library-only
sandbox probe. Actual service startup, ingestion and disablement remain unstarted
until this review is approved. Comparisons remain paused.
