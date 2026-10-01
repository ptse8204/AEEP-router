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

Exact bundle SHA-256: `4929c57fac7d53a468a95585d5c6362ac747df85e7611faa96f931972ceb7d7b`.

Definitions: [review bundle](worker-inspection-corrected-review-bundle.json).
This is a supporting inspection, not complete conformance. Credential canaries,
cross-worker access, candidate absence and complete permission evidence remain
separate requirements. The full four-family campaigns still need a later exact
budget amendment.

## Correction being reviewed

The original approved requests returned identity, model and inventory observations,
but their command crashed when the sandbox denied socket creation. The corrected
program catches that denial, closes any created socket, and distinguishes a hidden
configuration path from a read-only filesystem or permission error. A real
offline Codex regression passed in both pinned images with credentials absent
and network disabled. The sandbox and reviewed endpoints are unchanged.

These are new requests. The previous results, usage and failed status are retained
in `worker-inspection-result.json`; this bundle cannot erase or replay them.
