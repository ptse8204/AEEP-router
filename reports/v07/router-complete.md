# AEEP 0.7 router completion

Revision: `0fe9f66d5a8dbe3542bbf1038bce1037ef35d8d1`
Release ready: `true`

| Check | Profile | Status |
|---|---|---|
| `exact-versioned-capability` | `core` | `PASS` |
| `input-output-schema-validation` | `core` | `PASS` |
| `hard-policy-before-scoring` | `core` | `PASS` |
| `request-cannot-weaken-policy` | `core` | `PASS` |
| `route-qualification-activation-drift` | `core` | `PASS` |
| `deterministic-ranking-tie-breaking` | `core` | `PASS` |
| `baseline-abstention` | `core` | `PASS` |
| `idempotency` | `core` | `PASS` |
| `unified-attempt-transitions` | `core` | `PASS` |
| `crash-recovery-no-blind-duplicate` | `core` | `PASS` |
| `receipt-accounting-integrity` | `core` | `PASS` |
| `privacy-defaults` | `core` | `PASS` |
| `managed-prompt-output-privacy` | `core` | `PASS` |
| `old-manifest-database-compatibility` | `core` | `PASS` |
| `database-migration-rollback` | `core` | `PASS` |
| `offline-operation` | `core` | `PASS` |
| `offline-verifier-network-guard` | `core` | `PASS` |
| `committed-secret-scan` | `core` | `PASS` |
| `generated-schema-consistency` | `core` | `PASS` |
| `critical-module-branch-coverage` | `core` | `PASS` |
| `fault-before-claim` | `core` | `PASS` |
| `fault-after-claim` | `core` | `PASS` |
| `fault-after-cash-reservation` | `core` | `PASS` |
| `fault-after-capacity-reservation` | `core` | `PASS` |
| `fault-before-external-invocation` | `core` | `PASS` |
| `fault-after-app-server-turn-start` | `core` | `PASS` |
| `fault-during-streamed-output` | `core` | `PASS` |
| `fault-before-validation` | `core` | `PASS` |
| `fault-during-settlement` | `core` | `PASS` |
| `fault-after-partial-release` | `core` | `PASS` |
| `fault-during-recovery` | `core` | `PASS` |
| `app-server-handshake-features` | `openai` | `PASS` |
| `app-server-executable-identity` | `openai` | `PASS` |
| `codex-auth-boundary` | `openai` | `PASS` |
| `account-identity-redaction` | `openai` | `PASS` |
| `account-switch-hmac-invalidation` | `openai` | `PASS` |
| `bounded-environment-allowlist` | `openai` | `PASS` |
| `runtime-model-discovery` | `openai` | `PASS` |
| `multi-window-quota` | `openai` | `PASS` |
| `per-turn-token-accounting` | `openai` | `PASS` |
| `model-reroute-recording` | `openai` | `PASS` |
| `approval-intersection` | `openai` | `PASS` |
| `approval-replay` | `openai` | `PASS` |
| `one-turn-managed-execution` | `openai` | `PASS` |
| `no-credential-file-reads` | `openai` | `PASS` |
| `fake-server-conformance` | `openai` | `PASS` |
| `capacity-resource-contract` | `marketplace_contract` | `PASS` |
| `transferability-enforcement` | `marketplace_contract` | `PASS` |
| `capacity-reservation-release` | `marketplace_contract` | `PASS` |
| `entitlement-binding` | `marketplace_contract` | `PASS` |
| `openai-self-only-rejection` | `marketplace_contract` | `PASS` |
| `provider-authorized-mock-transfer` | `marketplace_contract` | `PASS` |
| `x402-local-batch-conformance` | `marketplace_contract` | `PASS` |
| `replay-expiry-double-spend` | `marketplace_contract` | `PASS` |
| `openai-live-account-proof` | `openai` | `SKIP` |
| `live-marketplace-networking` | `marketplace_live` | `DISABLED` |
