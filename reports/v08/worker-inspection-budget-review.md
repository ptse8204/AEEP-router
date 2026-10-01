# Post-login worker inspection review

Status: **unapproved**. This scope uses the two existing signed-in worker bindings.
No new login or model turn is requested.

| Item | Bound |
| --- | --- |
| Grant | Existing `onboarding`; ceilings and usage retained |
| New operations | Two, one per worker |
| Model turns and cash | Zero |
| Reserved elapsed time | At most 240 seconds combined; 120 per worker |
| Inspection deadline | 90 seconds plus bounded transport/worker cleanup |
| Current usage | 308 operations, 4 reserved turn allowances, 279.38554054975975 seconds; cash 0 |
| Credentials | Codex retains ownership; no login output or credential files read |
| Permissions | Fixed command uses the configured sandbox; no profile override |
| Purpose | Observe policy and declarations; test synthetic workspace/configuration writes and command networking |
| Authority excluded | No candidate assessment, plugin activation, budget expansion or automatic conformance approval |

The fixed command is in `src/aeep/hosts/codex_inspection.py`, bound through the
runtime digests in the bundle. It creates/removes synthetic marker files only,
tries TCP connections to the reviewed proxy and 1.1.1.1:443 without sending task
data, and reports results. It does not read credential files or task answers.
Policy responses are reduced to matches against listed expectations. Inventory
is skipped unless empty MCP configuration and disabled apps are observed, because
inventory discovery can itself initialize servers. Failures retain charges and
partial evidence; these request IDs cannot be automatically retried.

Exact bundle SHA-256: `140a80558586d7efb5c798ecde0e0c8da5a7e053e45c3b4188094f7bd53dc38a`.

Definitions: [review bundle](worker-inspection-budget-review-bundle.json).
This is a supporting inspection, not complete conformance. Credential canaries,
cross-worker access, candidate absence and complete permission evidence remain
separate requirements. The full four-family campaigns still need a later exact
budget amendment.

## Superseded before approval

The local-search worker-delivery fix changes runtime dependency digests. This
bundle is now historical and must not be approved or executed against the changed
source. It has consumed no operations or turns. A replacement exact review will
be prepared after the implementation and checks are complete; previous approval
questions do not authorize the changed snapshot.
