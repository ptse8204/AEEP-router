# Prepare the private Langfuse runtime

The ordinary workflow now has a minimized canonical receipt-export adapter.
Actual Langfuse deployment, ingestion, linkage and disabled-export observations
remain unverified. This directory contains read-only source/OCI preparation;
no image layer, compiler, service or task program was executed.

The original pin `c106bb3d945323688e6f6079f65fb0ab28203b53` has no matching
published SHA-tagged web/worker image in either queried registry. The published
4.55.0 images identify `5e4db922e9021083500cd066249b220a414b7dfe`. The
selected catalog moves to that exact release for the deployment proposal. Its
OTLP API definition is byte-identical to the original pin; full runtime
compatibility still needs actual checks. All original observations remain.

[Verified original source bindings](verified-source-bindings.json) retain the
release compose file, license, both Dockerfiles and both OTLP API definitions.
The root license distinguishes MIT core from enterprise directories and
third-party licenses. The image labels alone supply no license determination.
Only the local core tracing path is proposed; no enterprise entitlement,
redistribution or publication authority is inferred.

All six ARM64 service manifests and configs now resolve at immutable digests.
The supporting image pins from October30 are preserved. The earlier MinIO config
failure is resolved through its anonymous public registry token flow. No private
credentials were used or retained. Compressed layer total is1,164,219,714bytes;
actual host growth is unknown until a reviewed pull. The50GiB reserve applies.

## Remaining review preparation

The concrete grouped acquisition/wheel/docs review is prepared beside the
[ordinary CLI increment](../workflow-telemetry-20261104/README.md). Downloading
the exact images permits static license and startup-permission inspection before
the separate service execution review. Retain all acquired images for reuse.

Before that service review:

1. Bind private Docker configuration, CLI/plugin fingerprints and every image
   digest. Preserve all existing images, containers, volumes and databases.
2. Use a new owned private network and owned volumes, expose only a loopback UI/
   OTLP port, and disable upstream telemetry, provider/AI and external features.
3. Generate only task-owned local credentials inside the reviewed private setup;
   do not read host credentials, provider setup or Codex state.
4. Verify ownership/permissions, launch and stop the private upstream services;
   send an actual canonical receipt through the ordinary CLI; verify ingestion
   and receipt/trace linkage; demonstrate disabled export without another send.
5. Retain the reusable runtime and evidence, preserving failed/partial charges.
   Independent package/docs components must continue after a service failure
   unless authority, cleanup or accounting is uncertain.

This is preparation, not an execution review or a passed integration. The current
new wheel needs a specific applicable artifact review. Comparisons remain paused.
