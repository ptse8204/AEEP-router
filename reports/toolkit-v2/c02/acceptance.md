# C02 acceptance mapping

Scope: additive, inert contracts. Execution, normalization from a live backend,
provenance authentication and comparison math remain C04/C05 work.

| Required check | Implemented evidence | Limit |
|---|---|---|
| Versioned extension, adapter, run, bundle, report and developer contracts | Seven generated `schemas/toolkit-*.schema.json` files and `aeep_toolkit.models` | Schemas validate declarations; they do not authenticate them. |
| Malformed versions and missing provenance rejected | `test_invalid_or_unsupported_run_claims_are_rejected` | References must later resolve to the canonical store. |
| Counterfeit actual-cash fields rejected | `actual_cost_usd` is forbidden; only an existing accounting reference is accepted | No new cash amount or billing authority is created. |
| Cached/reasoning overlap retained without double counting | `test_token_subsets_and_unknowns_are_not_additive_totals` | Source semantics remain explicit; C05 supplies comparisons. |
| Unsupported telemetry and hosts rejected | `test_adapter_rejects_unsupported_host_identity_or_telemetry` | Actual host conformance remains unverified. |
| Candidate and adapter identity binding | `test_bundle_binds_candidate_artifact`, duplicate and adapter checks | Worker differential conformance remains C04/C07. |
| Install permissions and pins required | `test_extension_permissions_and_pins_are_required` | C03 must resolve installed state, license policy and full transitive effects. |
| No required routing/orchestration/server imports | Fresh-process `test_contract_import_does_not_load_legacy_runtime` | Existing distribution dependencies are unchanged; minimal installation remains C06. |
| Legacy evidence preserved | No existing runtime module or schema modified; full regression checks | No automatic migration upgrades incomplete historical evidence. |
| Synthetic outcomes cannot claim live demonstrated benefit | `test_synthetic_report_cannot_claim_demonstrated_benefit` | Live verdicts still require authenticated analysis and predeclared thresholds. |

Full integrated commands and outcomes are in `checks.json`; supplemental Node,
proof, package and docs evidence is separate. Pending commands are not passes.
