# Protected worker bootstrap review

Status: **approved and applied on September 24, 2026**. The exact bundle is unchanged; [the approval record](connectivity-approval.json) records its digest and unchanged counters. This replaces the earlier two-operation draft and includes sign-in setup time.

| Item | Bound |
| --- | --- |
| Existing grant | `onboarding`; 300 turns / 3,600 seconds; unchanged |
| Existing consumption | 302 operations; two reserved turn allowances; 93.31732538260985 seconds; cash zero |
| New sign-in setup | Two operator-terminal operations, each at most 300 seconds plus 30 seconds cleanup allowance; zero model turns |
| New connectivity probes | Two operations, each at most one model turn and 65 reserved seconds |
| Total new reservation | At most four operations, two model turns and 790 seconds from the existing grant |
| Data and cash | Existing restrictions retained; no arbitrary candidate egress, no cash expenditure |
| What this cannot approve | Candidate assessment, plugin activation, full conformance, production readiness or a larger budget |

Exact bundle SHA-256: `592d5610a6bf91262c4bf4d2cd8126fbbc6e30af1b8dc239a8b73339011f5657`.

The bundle binds the two immutable images, reviewed files, proxy image/configuration, private network, adapter implementation and runtime digests. Sign-in uses Codex inside the protected worker volume. AEEP never reads or copies desktop authentication or captures login output. Failed/uncertain operations remain recorded and cannot replay the same request.

Both sign-ins and both connectivity probes completed on September 24, 2026. See [the bootstrap result](connectivity-bootstrap-result.json). The commands below are retained for history; do not rerun these one-shot requests.

```bash
PYTHONPATH=src python3 -m aeep assess --manifest .aeep/live-review-v3/aeep.json signin-worker conformance_probe_da6b66f5899e45ea99b75efcac4c002f
PYTHONPATH=src python3 -m aeep assess --manifest .aeep/live-review-v3/aeep.json signin-worker conformance_probe_d38897e8093a4d75a4eae632b8d6b479
```

A successful login process is only a prerequisite. Post-login identity, effective permissions, complete boundary checks and the separately budgeted pilot still follow. The full four-family experiment will need a concrete later budget amendment; this bundle does not fund it.
