# ADR-008: Capacity and transferability

Status: accepted for AEEP 0.7.

## Decision

Capacity keeps provider-local units and evidence. Subscription capacity defaults
to `SELF_ONLY`; private opportunity-cost valuation is routing policy, not cash.
Reservations use atomic compare-and-set state. External execution entitlements
require explicit provider-authorized evidence and exact resource, beneficiary,
capability, action, quantity, expiry, and nonce binding. Unknown capacity cannot
authorize transfer.

## Rejected alternatives

- A global synthetic token: rejected because unrelated provider quotas are not
  fungible and conversion would erase raw evidence.
- Treat zero incremental subscription cash as free: rejected because scarce quota
  has opportunity cost and unknown cost is not zero.
- Assume a personal subscription is shareable: rejected because AEEP has no
  provider authorization for resale or delegation.
- Let a signed provider claim become an observation: rejected because a signature
  proves authorship, not truth or local measurement.

## Consequences

Old resources parse with safe defaults. Personal OpenAI capacity cannot issue an
external entitlement. A future transferable resource must supply explicit local
trust policy and provider authorization before issuance or settlement.
