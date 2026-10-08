# AEEP 0.6 provider trust

Decide whose signed claims your router may accept and what each signer is
allowed to attest. Explicit roles keep package provenance separate from evidence
about correctness or resource use.

This 0.6 trust contract remains supported; its version does not identify the
latest AEEP release. See [provider packages](PROVIDER_PACKAGES.md) for validation
and [the operator guide](ECONOMIC_OPERATOR_GUIDE.md#2-establish-provider-trust)
for setup.

[Documentation index](README.md).

An embedded key can verify a package revision's integrity. Its identity remains
`self_asserted` until local policy pins the key.

Trusted keys have explicit roles:

- `provider_record`
- `package_publisher`
- `evidence_producer`
- `independent_verifier`
- `registry`

Existing 0.4 keys default only to `provider_record`. Rotation may narrow but
never expand roles, providers, capabilities, hosts, package IDs, or assigned
trust. Revocation always wins.

A package-publisher signature proves package provenance. It does not prove the
correctness, latency, token, or cost claims of an evidence artifact. Independent
evidence uses a separate domain-separated attestation bound to the artifact
digest, exact route fingerprint, workload, summary, producer, and validity.

Marketplace labels, registry ownership, image provenance, and download counts
remain metadata unless local policy recognizes a specific signer and role.
