# AEEP 0.7 subscription-native router

AEEP 0.7 routes an already-classified, versioned `ActionRequest` among qualified
implementations. Planning and generic tool discovery remain host concerns; native
Tool Search may identify a capability, but AEEP selects only among locally
permitted implementations of that exact capability.

## Release scope

- Add provider-neutral capacity observations, reservations, and execution
  entitlements while preserving raw provider units.
- Keep legacy delegated `host` behavior and add a distinct `host_managed`
  executor for reviewed local host adapters.
- Integrate the official Codex App Server as the first managed-host adapter;
  Codex owns login and credentials.
- Score subscription scarcity as private opportunity cost, never as provider
  cash or settlement evidence.
- Unify durable execution attempts and fail closed after an uncertain start.
- Provide offline x402 v2 batch-settlement conformance contracts. Live payment,
  custody, wallets, cryptocurrency, and marketplace operation remain absent and
  disabled.
- Ship one digest-bound, offline completion verifier. Live account validation is
  reported separately and may be skipped.

## Compatibility

Versions 0.1 through 0.6 remain readable. Existing manifests default subscription
resources to `SELF_ONLY` and `SUBSCRIPTION_USAGE`; existing `host` routes retain
delegated semantics. New managed-host routes require local configuration,
qualification, activation, and approval.

## Delivery gates

Each implementation area has deterministic offline tests. Final readiness is
derived by `aeep verify router-complete --profile all --strict --json`; no live
marketplace or personal-account execution is required or implied.
