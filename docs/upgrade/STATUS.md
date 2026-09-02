# AEEP 0.7 upgrade status

Baseline revision: `405a74433df1707823c59597dabd84ba9aaa19cf`

| Phase | State | Next executable step |
|---|---|---|
| 0. Baseline | COMPLETE | Baseline preserved in `reports/v07/baseline.json`. |
| 1. Protocol boundary | COMPLETE | Decisions frozen in ADR-007 through ADR-009. |
| 2. Capacity contracts | COMPLETE | Capacity contracts and SQLite schema 6 verified. |
| 3. Managed-host seam | COMPLETE | Provider-neutral adapter and executor verified. |
| 4. Codex App Server | COMPLETE | Fake-server transport and managed adapter verified. |
| 5. Quota routing | COMPLETE | Multi-window pressure and pre-invocation revalidation verified. |
| 6. Durable attempts | COMPLETE | Unified attempts and SQLite schema 7 verified. |
| 7. Tool Search proofs | COMPLETE | Four host-native routing campaigns verified. |
| 8. x402 contracts | COMPLETE | Offline local batch binding verified. |
| 9. Operator CLI | COMPLETE | Host, capacity, and x402 operator commands verified. |
| 10. Completion verifier | COMPLETE | Digest-bound executable verifier returns release-ready. |
| 11. Security closure | NOT_STARTED | Update threats and negative tests. |
| 12. Release-candidate pass | NOT_STARTED | Run the full release matrix. |
| 13. Documentation | NOT_STARTED | Update public docs and final review. |

Files changed: baseline/version files; `AGENTS.md`, `SPEC.md`, `ARCHITECTURE.md`, `SECURITY.md`; roadmap, migration guide, and ADR-007 through ADR-009.

Migrations added: SQLite schema 6 adds capacity observations, reservations, authorization evidence, entitlements, and redemptions. SQLite schema 7 adds durable execution attempts and transition history.

Tests run: compile, Ruff, mypy, schemas, 582 Python tests, 13 Node tests, all CI proof checks, coverage, and build passed. Baseline total coverage: 80%.

Phase 2: 57 capacity, migration, and provider-package tests passed; Ruff, mypy, and schema generation passed.

Phase 3: managed-host router, registry collision, legacy host, provider-package authority, Ruff, mypy, compile, and schema checks passed.

Phase 4: added a bounded persistent App Server transport, sanitized account/model/quota observations, approval intersection, one-turn execution, token/reroute accounting, operator-only login service, and a credential-free fake server. Ruff, mypy, compile, schemas, and 37 focused transport/adapter/router tests passed.

Phase 5: mapped all raw quota windows to a conservative maximum-pressure routing view; exposed pressure, reset, uncertainty, and private valuation score components; refreshed before scoring and revalidated once before invocation. Forty-four focused scoring, router, and adapter tests passed; Ruff, mypy, compile, and generated schemas passed.

Phase 6: ordinary, managed-host, and prepared execution now share a durable compare-and-set attempt state machine with leases, heartbeats, reservation bindings, invocation evidence, external identity digests, and terminal receipts. Fault persistence, two-worker exclusion, managed crash/no-duplicate, all prepared recovery tests, the full Python suite, Ruff, mypy, compile, and generated schemas passed.

Phase 7: exact local bypass, managed single-turn, native Tool Search coexistence, and the extra-round meta-router negative control are captured in a typed, schema-checked proof report. Eighteen focused proof, Codex-adapter, and managed-host tests passed; Ruff, mypy, compile, and generated schemas passed.

Phase 8: added an optional `aeep-local` x402 v2 batch binding over the existing capacity entitlement ledger. The credential-free campaign proves canonical commitment, authority/action/beneficiary/maximum binding, replay, expiry, partial release, double-redemption rejection, SELF_ONLY rejection, and overclaim dispute with live networking disabled. Nineteen focused capacity, x402, and CLI tests passed; Ruff, mypy, compile, and generated schemas passed.

Phase 9: added non-billable Codex doctor/account/models/quota diagnostics, an explicit operator-only login command, capacity list/status/reservations commands, and automatic construction of the official adapter from reviewed local managed-host configuration. The OpenAI example is runtime-discovered and SELF_ONLY. Twenty-eight focused CLI, adapter, managed-host, and x402 tests passed; Ruff, mypy, compile, example parsing, and generated schemas passed.

Phase 10: `aeep verify router-complete --profile all --strict --json` now executes the required pytest nodes, verifies their locked SHA-256 evidence artifacts, and derives readiness. The report contains 34 PASS checks, one allowed live-account SKIP, and one DISABLED live-marketplace check; all three offline profiles PASS and `release_ready` is true. Tamper detection and deterministic tie-breaking tests pass; Ruff, mypy, compile, and generated schemas pass.

Proof/report paths: `reports/v07/baseline.json`, `reports/v07/baseline-coverage.json`, `reports/v07/host-native-routing.json`, `reports/v07/x402-conformance.json`, `reports/v07/verification-lock.json`, `reports/v07/router-complete.json`, `reports/v07/router-complete.md`.

Unresolved risks: the literal `python` command is unavailable on this host; baseline and release checks use `python3` and record that substitution. Live Codex login and model execution remain intentionally untested pending explicit operator approval.
