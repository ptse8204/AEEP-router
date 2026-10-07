# AEEP 0.6 provider packages

For publishers and operators exchanging an inert capability package. Install
AEEP and run the examples from the repository root. Read
[provider trust](PROVIDER_TRUST.md) and [evidence reuse](EVIDENCE_REUSE.md)
before treating a valid signature as useful routing evidence.

[Documentation index](README.md).

`aeep-provider.yaml` publishes provider identity, exact capability contracts,
inert route declarations, content-addressed artifacts, evidence references, and
bounded smoke definitions. It never grants activation or approval.

Version 0.6 evidence must declare its authority class and exact portable cohort.
Version 0.5 packages remain readable, but evidence missing those declarations is
capped as a weak prior and cannot qualify a route by itself.

```bash
aeep provider validate examples/provider_package/aeep-provider.yaml
aeep provider digest examples/provider_package/aeep-provider.yaml
aeep provider verify examples/provider_package/aeep-provider.yaml
aeep candidate ingest examples/provider_package/aeep-provider.yaml
```

The signed payload is RFC 8785 canonical JSON containing only `apiVersion`,
`kind`, `metadata`, and `spec`. Ed25519 signs the domain-separated SHA-256
digest. Formatting, YAML comments, and key order do not affect the digest.

Manifests must use strict JSON-compatible YAML and fit within 1 MiB. The parser
rejects aliases and duplicate keys, limits nesting to depth 32, and bounds
collection sizes. Artifact paths are relative to the manifest directory. Absolute paths, traversal, symlinks,
unknown compression, and archive extraction are rejected.

Accepted local or opt-in HTTPS artifacts are copied into immutable SHA-256 CAS
storage before parsing. Ingest may download explicitly allowed evidence bytes;
it never starts a command/MCP server, imports external Python, authenticates,
executes, smokes, qualifies, or activates a route.

Package command routes use portable executable/package identities. Local
runtime resolution happens after ingest and is revalidated before smoke and
execution. A package cannot rely on a platform-specific absolute path as its
portable evidence fingerprint.

Published Python routes use subprocess isolation with bounded JSON pipes and
timeout termination. This is a process boundary, not a replacement for a
container or VM when provider code is untrusted.

Providers may publish signed discovery metadata at
`/.well-known/aeep-provider.json` and validate a package with `aeep provider
conformance PATH`. Discovery and conformance remain inert: they do not grant
trust, install, qualify, activate, or execute.
