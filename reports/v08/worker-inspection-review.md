# Post-login worker inspection review

Status: **approved and executed** on September 25, 2026. This scope uses the two existing signed-in worker bindings.
No new login or model turn is requested.

| Item | Bound |
| --- | --- |
| Grant | Existing `onboarding`; ceilings and usage retained |
| New operations | Two, one per worker |
| Model turns and cash | Zero |
| Reserved elapsed time | At most 240 seconds combined; 120 per worker |
| Inspection deadline | 90 seconds plus bounded transport/worker cleanup |
| Current usage | 306 operations, 4 reserved turn allowances, 276.6424535077531 seconds; cash 0 |
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

Exact bundle SHA-256: `f0abf2cbf701f3560bb4a9cd5a80e89565ff6d6e9180211ca8ecdb53f04d5db4`.

Definitions: [review bundle](worker-inspection-review-bundle.json).
This is a supporting inspection, not complete conformance. Credential canaries,
cross-worker access, candidate absence and complete permission evidence remain
separate requirements. The full four-family campaigns still need a later exact
budget amendment.

Both one-shot requests completed with partial observations and confirmed cleanup.
No model turn started. A probe bug stopped the command when socket creation was
denied; the failed results and 2.743 seconds of usage remain recorded. See
[approval](worker-inspection-approval.json), [results](worker-inspection-result.json)
and [offline reproduction](inspection-offline-reproduction.json). These request
IDs must not be replayed. A corrected implementation requires fresh review and
new request IDs.
