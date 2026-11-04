# Connect canonical receipt export to the ordinary workflow

`workflow export-telemetry` selects a disabled-by-default, reviewed local
Langfuse destination and a source receipt from the existing accounting store.
The existing HTTP executor sends only the minimized OTLP payload. It adds no
scheduler, database, service manager or background exporter.

The exact preview binds the receipt digest, destination, exporter fingerprint
and source. The existing repository reserves the nested export operation and
the wrapper separately. Wrapper timing excludes that nested interval. A durable,
deterministic export identity blocks replay through another CLI operation key.
Failure charges and partial observations remain. Disabled export reads no local
authentication; revoked definitions fail before invocation. Receipt provenance
does not upgrade provider claims into independently measured usage.

Prompts, artifact contents, paths and credential values are excluded. The sole
eligible authentication variable is task-owned `AEEP_LANGFUSE_LOCAL_AUTH`; no
provider or Codex credential is read. The destination is a literal loopback IP
with a strict unprivileged port, redirects and environment proxies disabled.
The shared HTTP executor now performs its final invocation authority check before
creating the request client. Old requests with no check retain their behavior.

Canonical records preserve raw transport resource dimensions, exclusive wrapper
measurements, source/transport receipt references, exporter fingerprint and trace
identity. HTTP200 with a rejected/invalid partial response stays failed. Accepted
transport cannot prove ingestion or trace linkage; both remain unverified.

## Source and runtime preparation

Langfuse source selection moves from `c106bb3d945323688e6f6079f65fb0ab28203b53`
to the published 4.55.0 release `5e4db922e9021083500cd066249b220a414b7dfe`.
Both registries returned404 for the former SHA-tagged web/worker images. The
4.55.0 OCI config labels identify the release commit, rather than the original
snapshot. Their OTLP API definitions have the identical original Git blob
`3ff63598128b16a2b701c72788a636fbc305a598`. This resolves source/artifact
compatibility for the deployment proposal; it asserts no whole-runtime equivalence.

[Pinned artifact preparation](../langfuse-runtime-preparation-20261104/README.md)
retains metadata and original source bindings. No image layers were fetched and
no Langfuse service, database or third-party runtime was started. New artifact,
service and task-owned credential authority is required before execution. Old
Langfuse evidence remains attached to its original pin and scope.

## Verification

Focused CLI, serialization, accounting, privacy, disabled/revoked authority,
partial-response, timeout and replay checks pass with first-party substitutes.
The real HTTP executor is exercised through an in-memory mock transport, not a
Langfuse server. The old unselected workflow serialization remains covered.

All 13 source gates pass on
`5a13a630a89aa0c6b4940be4eed0a30dd80ab5a822ee15f7f25f78f521c11c4b`.
Both full runs passed 2,134 tests with 21 skips; combined coverage is
82.697017447269%, and both branch gates pass. Schemas, policy, lint, typing,
integration fixtures and build also pass. Minimum sampled host free space was
66.60 GiB. [Exact results](verification/checks.json) and the
[408-file frozen source inventory](source-snapshot.json) preserve the tested
working tree, including the operator's separate CI test/development pin. Those
unrelated changes remain outside the feature commit.

The new wheel is `5fe1fa9ba780d4ae6de808ca5d1681c5f84ee9ba879b404ef58971e73a751088`.
Its private installation plan binds the same 32 cached dependencies. No install
has occurred. A standard-library-only boundary probe passes, and five substituted
acquisition-driver scenarios preserve old counters and settle failed operations.
These are first-party engineering controls, not upstream functional evidence.

## Next exact approval

The [grouped review](operation-review.json) covers acquisition of the six pinned ARM64 images, inspection
of their immutable references, the new wheel and cached offline documentation
tools. The new isolated artifact grant uses the existing canonical database;
all old grants/counters remain. Its ceiling is 31 operations, zero model turns,
4,200 reserved seconds and $0 cash authority. Six ordinary pulls plus inspections
and exclusive driver overhead use 13 operations. At most two attempts per immutable
download are permitted; independent images continue after a settled failure.
Twelve further read-only streamed image audits fit the same finite envelope.
There is no disk archive, guest-code execution or host executable extraction.

Images and reusable runtimes stay. Acquisition needs 6 GiB start headroom over
the normal 50 GiB reserve; the actual reserve is monitored during a pull. No
container, service, credential, model, candidate admission or release is authorized.
After acquisition, inspect licenses and startup permissions before preparing the
separate private-service execution review. Do not infer installed or functional
Langfuse readiness from a successful download.

The current guide and wheel still need their exact installed/offline-doc checks.
Historical successful components are not replayed under terminal older reviews.
Comparisons and all usefulness gates remain paused/unassessed.
