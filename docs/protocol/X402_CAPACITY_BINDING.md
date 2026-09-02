# AEEP local x402 capacity binding

The AEEP 0.7 binding implements only offline x402 v2 batch semantics:
`commit -> accumulate -> redeem/reconcile`. It carries a resource-specific unit,
backing-resource fingerprint, exact action and beneficiary binding, maximum
quantity, expiry, nonce, entitlement digest, authority evidence ID, and signature.
It is not cash.

The binding is disabled by default. `aeep-local` creates no network connection,
wallet, token, stablecoin, custody, payout, or real-value transfer. A
`SELF_ONLY` or `SAME_PRINCIPAL` entitlement is rejected before commitment
serialization. Consequently, personal OpenAI subscription capacity cannot be
committed for an external beneficiary.

Provider-authorized mock capacity is the sole positive conformance path. The
shared SQLite entitlement ledger enforces unique nonces, attempt-bound idempotent
redemption, expiry, maximum quantity, release, and compare-and-set updates. The
x402 accumulator separately rejects replayed evidence and disputes an overclaim.
A signature proves the recorded authorization binding only; it does not establish
service quality, route qualification, honest metering, or activation authority.

Run the credential-free proof with:

```bash
aeep x402 conformance --binding aeep-local --json
```

The report labels live networking `DISABLED` rather than `PASS`.
