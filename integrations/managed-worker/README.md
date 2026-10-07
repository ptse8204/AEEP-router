# Managed worker image contract

For operators preparing controlled assessment environments, not ordinary
host connections. Read the [testing policy](../../docs/ASSESSMENT_TESTING.md)
first. Check host free space and Docker usage before builds; keep at least
50 GiB free, pin all resources, and retain current and rollback images.

[Documentation index](../../docs/README.md).

Build two immutable Linux images from the same reviewed base and Codex binary.
Place `worker-launch` at `/opt/aeep/worker-launch` with executable permissions,
reviewed Codex `-c` overrides (a JSON string array) at
`/opt/aeep/worker-config.json`, and only the selected arm's reviewed dependencies
in the image. Use a non-root UID/GID 65534 and create `/worker/auth` owned by that
user. Do not include credentials, the repository, generators, expected answers,
future cases or contributor instructions in an image.

`ManagedWorkerBinding` pins the image, binary, configuration, dependencies and
resource limits. It allows no host bind mounts, host networking, privileged mode
or Docker socket mount. Each invocation gets private home, temporary and work
directories. Optional credential volumes must differ between arms and are for
Codex-managed worker login only. Volume separation does not establish credential
protection from trial tools: the canary and effective-policy checks remain
mandatory. No desktop credentials may be copied.

The default denies all network. A reviewed immutable Docker network ID can be
selected only after its external enforcement policy restricts the model-service
connection separately from agent commands. Selecting a network ID alone does
not verify egress enforcement.

The image contract and process arguments are not conformance evidence. The
canonical [testing policy](../../docs/ASSESSMENT_TESTING.md) requires actual
boundary and host checks before model assessment. Fresh process launch is
implemented; reuse across cases requires separate reviewed lifecycle evidence.

<details>
<summary>Contents</summary>

- [Linux build and security profiles](#linux-build-and-security-profiles)
- [Capable local comparison images](#capable-local-comparison-images)
- [Model connectivity review](#model-connectivity-review)
- [Paired offline boundary probe](#paired-offline-boundary-probe)
- [Local catalog metrics](#local-catalog-metrics)

</details>

## Linux build and security profiles

The Dockerfile consumes a reviewed local context with the Codex Linux binary,
its code-mode host, ripgrep and `codex-resources` from the same verified release.
Add `worker-launch`, `worker-config.json`, `requirements.toml`, and the selected
arm's `dependencies/` and `skills/`. Empty dependency/skill directories are valid
for the baseline. Build with `docker build --network=none`, record the resulting
image digest, and bind that digest before any campaign. The build contains no
login step, test answers or dependency-probe programs.

Worker contract v2 accepts an exact `seccomp_profile` JSON object and a named
`permissions_profile`. These fields change the worker digest and require review
and a scope amendment using the original grant counters. Both arms must have
identical profiles. AEEP writes the seccomp definition into a private temporary
file for Docker, verifies its content, and removes it when the adapter closes.
It is not mounted into the worker. Without a custom definition, the worker uses
Docker's default policy.

`nested-sandbox-seccomp.example.json` is an unapproved review template based
on Moby's default profile with namespace operations added for Codex's nested
bubblewrap sandbox. `requirements.example.toml` is also a review template.
One local allowed-command/denied-canary probe passed with these definitions;
that does not establish the complete enforcement boundary. Never enable them
merely because they are bundled here. Recheck the installed host version,
managed policy, canaries and all required conformance probes after review.

Exec uses the named `default_permissions` setting without a conflicting legacy
sandbox flag. App Server sends the reviewed profile on thread creation and requires matching
acknowledgement. Acknowledgement alone is not conformance: scoped invocation
also requires a current boundary reference supplied by the controlled authority
check. Revocation is checked again immediately before dispatch.

## Capable local comparison images

`Dockerfile.incremental` derives both arms from the same pinned reviewed Linux
image, installs the hash-locked wheels in `requirements-linux-arm64.lock`, and
adds the existing reviewed Spreadsheets package only to treatment. Download the
listed Linux CPython 3.13 wheels into a separate build context; build with
`--network=none --pull=false`. Copy `worker-launch`, `capable-local-config.json`
(as `worker-config.json`) and the lock file (as `requirements.lock`) into that
context. Select the `common` and `treatment` targets and retain their resulting
image digests. The named base images must resolve to the exact digests in the
Dockerfile. There are no authentication files in the context.

The recorded `reports/v08/incremental-worker-review.json` checks both images with
real Codex Linux sandbox processes: pandas/openpyxl workbook round trips work in
both; the selected package and artifact-tool are absent from control and present
in treatment. These are unauthenticated dependency checks, not conformance or
plugin benefit evidence. Review the final egress, permissions and protected login
before model execution. These images have network access disabled.

## Model connectivity review

`proxy/` contains a standard Squid configuration and pinned package build recipe.
Use a private Docker network created with `--internal` for workers. Attach only
the proxy to that network and an outbound network, without publishing a host port.
The configuration permits HTTPS CONNECT only to the reviewed authentication/model
hosts, denies private destinations, disables caching and access logging, and
keeps TLS end to end. Pin the resulting proxy image and private network ID.
`model_proxy_url` supplies its exact IPv4 address and port to Codex. Network and
proxy bindings must match between arms; neither setting alone proves enforcement.

The current unauthenticated probes are recorded in
`reports/v08/incremental-proxy-probe.json` and
`reports/v08/incremental-network-boundary-probe-final.json`: the authentication
CONNECT succeeds, unrelated destinations/direct egress fail, and commands in both
Codex sandboxes cannot reach the proxy or read a synthetic credential canary.
These records do not authorize model trials or establish post-login conformance.

The installed Linux binary accepts `codex sandbox --permission-profile aeep
--include-managed-config COMMAND...`; inspect the pinned binary's help before
repeating the probe. Do not substitute undocumented flags or relax the sandbox
when a command is rejected. Sign in through `codex login --device-auth` inside
the protected worker volume, after scope review. Never copy desktop credentials.
Official documentation distinguishes command-network restrictions from model/auth
connections: [network security](https://learn.chatgpt.com/docs/agent-approvals-security)
and [device login](https://learn.chatgpt.com/docs/auth).

Repeat the unauthenticated command/canary checks with the checked-in probe:

```bash
PYTHONPATH=src python3 scripts/probe_managed_network.py \
  --workers reports/v08/incremental-worker-review.json \
  --proxy-image sha256:REVIEWED_LOCAL_PROXY_IMAGE_DIGEST \
  --output reports/v08/network-probe.json
```

The probe refuses credential volumes and removes its temporary networks and
containers. Its output is an observation, never automatic conformance approval.

For protected sign-in, use the operator-terminal `aeep assess --manifest MANIFEST
signin-worker REQUEST` command after approving the exact bootstrap environment.
It forwards Codex's device-login display directly to your terminal, reserves setup
time on the same grant, and removes the temporary worker on completion or
interruption. It does not capture login output or verify post-login permissions.
See [the testing runbook](../../docs/ASSESSMENT_TESTING.md#protected-worker-sign-in).

## Paired offline boundary probe

Run both pinned workers together without credentials or networking:

```bash
PYTHONPATH=src python3 scripts/probe_managed_pair.py \
  --workers reports/v08/offline-inspection-fixture-specs.json \
  --output reports/v08/new-offline-pair-observation.json
```

The input contains exactly two explicit executor definitions, control then treatment.
The probe refuses credential volumes, network bindings and alternate entrypoints.
It uses the normal worker launcher and App Server command sandbox, with no model
turns or permission override. Synthetic markers check separate workspaces,
external-answer exclusion and the protected credential directory. It reads actual
cgroup limits, checks shared pandas/openpyxl operations, verifies Spreadsheets
paths and aliases differ, and exercises its bundled artifact-tool and authoring
helper. An interrupted command must end when its worker is removed. The probe
cleans up every worker it starts, including after a partial failure.

The output preserves sanitized observations and source/worker identities. It
refuses an existing output path. These offline observations do not establish
post-login conformance, complete tool permissions, discovery telemetry or model
benefit. Repeat the applicable checks through a separately reviewed authenticated
operation before admitting a managed workflow. The script cannot sign in, approve
a definition, reserve subscription turns or write a conformance admission.

Local-search routes use a reviewed `local_search_tree:2` input mapping with explicit
coordinator read roots, plus `input_tree: "local_search_tree:1"`. The existing
worker transport copies only the selected case's UTF-8 files into a fresh
`/workspace/case-tree`; it never mounts the coordinator directory. Limits are
1,000 entries, 100,000 content bytes and 32 path components. Duplicate names,
file/directory collisions, credentials filenames, symlinks and traversal are
rejected. Query and path evaluation still belongs to the worker. The transport
stages file contents outside the task prompt. App Server supports this transfer;
Exec remains explicitly ineligible for it. This capability is functional support,
not an attestation of an authenticated worker's permissions.

For authenticated boundary observations, use the operator-reviewed
`prepare-pair-inspection` / `inspect-pair` assessment commands. Their first fixed
profile covers Spreadsheets, shared pandas/openpyxl, synthetic canaries, policy,
network denial, resources and interrupted-worker cleanup. It reuses the offline
probe's bounded commands and the assessment grant/event store. It cannot start
model turns, sign in, approve conformance or activate a candidate. See
[the testing guide](../../docs/ASSESSMENT_TESTING.md) for authority and accounting.

## Local catalog metrics

The optional App Server `adapter_options.catalog_metrics=true` uses the existing
worker launcher and stdio connection. Copy the installed
`aeep/hosts/codex_metrics.py` into the build context as `codex_metrics.py` and bind
its SHA-256 under `/opt/aeep/codex_metrics.py` in `reviewed_files`. Both packaged
Dockerfiles include it. The adapter rejects missing or different collector code;
old images and configurations remain usable with this option absent.

The relay listens only on worker loopback, disables log/trace export, and directs
OTLP JSON metrics to that local listener. It enables the analytics switch needed
by the pinned Codex metrics pipeline. Review the resulting effective telemetry
configuration and network enforcement before authenticated use; local collection
does not authorize upstream telemetry destinations. Required collector isolation
must cover task commands and supporting integrations. A new image/configuration
requires fresh conformance. Do not enable this on an existing reviewed live
profile without that review.

Only four native metrics are retained: skill injection and enabled/kept/truncated
catalog counts. Their service tag must match the fresh worker. Skill identifiers
are hashed, catalog surfaces stay separate, and numeric values, batches, bytes
and distinct observations are bounded. Unknown attributes, raw payloads, logs,
account identifiers and task content are not retained. Invalid batches remain
explicit. Metrics are supporting observations and are never added to task usage.

The final receipt retains partial snapshots and a canonical digest observation.
Closing the collector does not prove complete upstream delivery. In particular,
missing injection metrics cannot establish non-use; catalog counts cannot prove
candidate-specific exposure; injection alone cannot prove invocation. All three
`capability_discovery` facts remain unknown until separately verified semantics
and boundary evidence support them. Native-catalog release gates remain unchanged.
