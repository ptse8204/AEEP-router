# AEEP 0.5 provider packages

`aeep-provider.yaml` publishes provider identity, exact capability contracts,
inert route declarations, content-addressed artifacts, evidence references, and
bounded smoke definitions. It never grants activation or approval.

```bash
aeep provider validate examples/provider_package/aeep-provider.yaml
aeep provider digest examples/provider_package/aeep-provider.yaml
aeep provider verify examples/provider_package/aeep-provider.yaml
aeep candidate ingest examples/provider_package/aeep-provider.yaml
```

The signed payload is RFC 8785 canonical JSON containing only `apiVersion`,
`kind`, `metadata`, and `spec`. Ed25519 signs the domain-separated SHA-256
digest. Formatting, YAML comments, and key order do not affect the digest.

Manifest input is limited to 1 MiB, strict JSON-compatible YAML, no aliases,
no duplicate keys, maximum depth 32, and bounded collections. Artifact paths
are relative to the manifest directory. Absolute paths, traversal, symlinks,
unknown compression, and archive extraction are rejected.

Accepted local or opt-in HTTPS artifacts are copied into immutable SHA-256 CAS
storage before parsing. Ingest may download explicitly allowed evidence bytes;
it never starts a command/MCP server, imports external Python, authenticates,
executes, smokes, qualifies, or activates a route.

Package command routes use portable executable/package identities. Local
runtime resolution happens after ingest and is revalidated before smoke and
execution. A package cannot rely on a platform-specific absolute path as its
portable evidence fingerprint.
