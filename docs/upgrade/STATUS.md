# AEEP 0.7 upgrade status

Baseline revision: `405a74433df1707823c59597dabd84ba9aaa19cf`

| Phase | State | Next executable step |
|---|---|---|
| 0. Baseline | COMPLETE | Baseline preserved in `reports/v07/baseline.json`. |
| 1. Protocol boundary | IN_PROGRESS | Write ADRs and migration guide. |
| 2. Capacity contracts | NOT_STARTED | Extend resource and accounting models. |
| 3. Managed-host seam | NOT_STARTED | Add the provider-neutral adapter boundary. |
| 4. Codex App Server | NOT_STARTED | Implement and test the transport adapter. |
| 5. Quota routing | NOT_STARTED | Add capacity pressure to routing. |
| 6. Durable attempts | NOT_STARTED | Unify attempt persistence and recovery. |
| 7. Tool Search proofs | NOT_STARTED | Add host-native routing campaigns. |
| 8. x402 contracts | NOT_STARTED | Add offline conformance binding. |
| 9. Operator CLI | NOT_STARTED | Add host/capacity/x402 commands. |
| 10. Completion verifier | NOT_STARTED | Add digest-bound verification. |
| 11. Security closure | NOT_STARTED | Update threats and negative tests. |
| 12. Release-candidate pass | NOT_STARTED | Run the full release matrix. |
| 13. Documentation | NOT_STARTED | Update public docs and final review. |

Files changed: `docs/upgrade/STATUS.md`, `reports/v07/upgrade-events.jsonl`, `reports/v07/baseline.json`.

Migrations added: none.

Tests run: compile, Ruff, mypy, schemas, 582 Python tests, 13 Node tests, all CI proof checks, coverage, and build passed. Baseline total coverage: 80%.

Proof/report paths: `reports/v07/baseline.json`, `reports/v07/baseline-coverage.json`.

Unresolved risks: the literal `python` command is unavailable on this host; baseline and release checks use `python3` and record that substitution.
