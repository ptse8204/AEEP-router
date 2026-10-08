# AEEP Toolkit architecture decisions (living log)

These are **proposed steering decisions**, not claims of implemented features. Append dated ADR-style entries to document new evidence and decisions. Do not retroactively edit benchmark parameters or rewrite historical AEEP records.

| ID | Initial decision | Reason | Reconsider if |
|---|---|---|---|
| D01 | Product is evidence-first plugin-value assessment and developer support | Original purpose; user-visible differentiation | User changes mission |
| D02 | Existing AEEP monorepo; feature branch; no full fresh-start rewrite by default | Preserve tests, history and reusable modules | C00 shows core cannot be safely isolated |
| D03 | Tiny core, modular AEEP extensions, optional legacy router | Avoid supporting two general-purpose agent platforms | C01 proves mandatory core needs a function |
| D04 | One benchmark engine first, chosen by measured adapter spike | Integration quality > number of libraries | Real trials favor a different engine |
| D05 | Natural selection control/treatment is primary evidence; forced-use separate | Prevent overstating optional capability benefit | Do not weaken this without explicit scientific rationale |
| D06 | Unknown cash/tokens are null; separate telemetry/estimates from actual spending | Prevent invented savings | Never overwrite missingness |
| D07 | Existing security/assessment authority remains in force | Product change does not create permissions | Only an explicit operator decision can revise it |
| D08 | Installation is preview-first with explicit component selection | Users must know the stack they are installing | Review tested user feedback |
| D09 | Full Toolkit is a catalog/profile, not install-everything-by-default | Some components are heavy, licensed, metered or host-incompatible | Only if all qualify on a target host |
| D10 | No new payout ledger/credit economy in early release | Funding is separate from resource savings | Proven user/developer demand |
| D11 | Static HTML/Markdown value reports first | Avoid hosting complexity | Users require an interactive report |

## Decision entry template

### DNN — YYYY-MM-DD — [title]
- **Status:** proposed / accepted / superseded / blocked
- **Problem & product impact:**
- **Alternatives:** (reuse / wrap / write / defer)
- **Observed evidence:** pinned URLs, commits, tests, license, interface results
- **Decision and rationale:**
- **Consequences, migration, rollback:**
- **Checkpoint linkage:** Cnn
