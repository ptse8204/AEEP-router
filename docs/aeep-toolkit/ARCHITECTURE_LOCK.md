# Architecture for the first complete toolkit

The operator confirmed a local Python CLI with HTML/Markdown reports. The
implementation follows the reuse decisions in [DECISIONS.md](DECISIONS.md),
starting with the pinned agent-skill-eval candidate. That candidate still needs
executable qualification; the toolkit does not yet run it.

| Responsibility | Implementation path | Current evidence |
|---|---|---|
| Evaluation harness | Adapt agent-skill-eval 0.7.0 at `59de161f657b82bfaf8f6abe83dfff38552deb21` | Source reviewed; C04 spike pending |
| Harness fallback | Existing AEEP controlled runner, only after a recorded comparison | Legacy checks pass; V2 conformance unresolved |
| Evidence and comparison | AEEP validates provenance, matched conditions, missing measurements and report conclusions | C02 contracts exist; C05 reports unfinished |
| Execution authority and accounting | Reuse existing reviewed definitions, finite allowances and canonical evidence | No second ledger; exact external dispatch integration unresolved |
| Worker isolation | Reuse reviewed controlled-worker mechanisms around the selected harness | Upstream temporary Git directories do not establish containment |
| Discovery | Existing ARD and MCP Registry clients | Preserve pinned interfaces; optional pack integration remains open |
| Security scanning | Optional Cisco Skill Scanner adapter | Source reviewed; no executable integration yet |
| Observability | Existing OpenTelemetry instrumentation; optional external exporters | No hosted service required by Essentials |
| Orchestration | Optional existing Router/StackRuntime and justified external adapters | No new mandatory workflow framework |
| Installation | Wrap existing installation review/recovery where applicable | Pure preview exists; dependency locks and real installer bridge unfinished |

## Withdrawn proposal

The implementation agent proposed extracting shared execution/evidence services
from Router before testing the external evaluator, and asked the operator to
choose extraction or a temporary legacy backend. That question omitted the
preferred external integration path and is withdrawn following the operator's
correction. No extraction was implemented, and no answer to that question is
needed. The [legacy source audit](../../reports/toolkit-v2/c04/extraction-audit.json)
records coupling, not a justification for a new execution architecture.

## Next implementation proof

Use agent-skill-eval's existing fake harness and deterministic graders for a
bounded no-charge engineering spike. Inspect its actual control/treatment
artifacts, optional exposure, failures and missing telemetry before writing the
small adapter. Retain upstream orchestration where it works. Add only the AEEP
validation and controlled-worker integration that the acceptance gates require.

External execution needs the exact reviewed scope. Fixture success will not
qualify host isolation, establish model savings or close C07. Broad internal
refactoring is not a prerequisite for preparing or reviewing this spike.
