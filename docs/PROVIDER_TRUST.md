# AEEP 0.6 provider trust

Cryptographic integrity and effective identity trust are separate. An embedded
key can prove that one package revision is internally consistent, but it is only
`self_asserted` until local policy pins that key.

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
