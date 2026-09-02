# ADR-009: x402 compatibility boundary

Status: accepted for AEEP 0.7.

## Decision

AEEP implements only an offline, disabled-by-default compatibility binding for
x402 v2 batch settlement: commit, accumulate, redeem/reconcile. The bound asset
is a resource-specific capacity unit with a backing fingerprint; it is not cash.
The conformance path performs no network or real-value transfer.

## Rejected alternatives

- Add a wallet, blockchain, stablecoin, facilitator, or custody dependency:
  rejected because none is needed to validate protocol binding.
- Call a live x402 endpoint in default tests: rejected because release readiness
  must remain offline, deterministic, credential-free, and non-billable.
- Serialize `SELF_ONLY` capacity first and reject later: rejected because the
  transferability violation must fail before any commitment is created.
- Treat settlement evidence as route qualification: rejected because payment
  authorization says nothing about capability correctness or activation.

## Consequences

The release proves replay, expiry, maximum, partial-use, release, and redemption
semantics locally. Marketplace operation remains `DISABLED`; live rails require a
separate product, security review, authorization model, and operator opt-in.
