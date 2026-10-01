# Worker conformance completion review

Status: **approved and executed** on September 25, 2026. Both connectivity calls and all 22 paired probes passed. See [approval](conformance-completion-approval.json), [validated events and accounting](conformance-completion-live-result.json), and [assembled conformance](conformance-completion-assembly.json). The immutable bundle retains its original proposal bytes.

The prior approved checks passed. This revision fixes two implementation gaps:
connectivity now commits individual events before completion, and new events bind
their journal identity to prevent nested-stream storage collisions. Conformance
also resolves the worker's execution hash to its separately hashed review document.
Historical identities, event bytes and successful observations remain unchanged.

| Item | Exact scope |
| --- | --- |
| Grant | Existing onboarding grant and usage counters |
| New operations | Four: two connectivity calls and two paired inspections |
| Model turns | At most two; no plugin tasks |
| Reserved elapsed time | At most 610 seconds combined |
| Cash, disclosure and login | Zero cash; unchanged disclosure; existing protected sign-ins |
| Worker/model settings | Existing pinned images, gpt-6-astra, medium reasoning |
| Current remaining allowance | 294 turns and 3298.433737368323 seconds |
| Review additions | Exact immutable managed policies, enforcement definition and semantic inventory bindings |
| Conformance assembly | Permitted only when fresh probes, identity, journal events and operations validate against these exact definitions |
| Excluded | Candidate campaigns, admission, activation and budget expansion |

Exact bundle SHA-256: `76cb66968107436e712faf09db7bba5972ee724f04383ab66f5272a1ffde3bf9`.
[Definitions and immutable scope amendment](bootstrap-events-review-bundle.json).

Both image configuration files and managed requirement files were inspected
without starting containers or mounting credentials. They are identical between
arms. Configuration hashes match the worker bindings. The proxy image contains
the packaged HTTPS destination allowlist. These files, image-layer lineage and
actual prior authenticated observations support the enforcement review; probes
alone cannot establish universal isolation. Inventory bindings describe the
reviewed shared environment and candidate addition, not a claim that the MCP
inventory endpoint enumerates every model-visible built-in tool.

The selected permission profile denies general command networking and credential
reads, permits shared local tools and private workspaces, and disallows apps,
MCP servers, browser/computer use, memories and subagents. Spreadsheets and its
exclusive dependencies are the reviewed treatment addition. Fresh observation
must still match the active profile, managed requirements and advertised skills.
Any mismatch leaves conformance unavailable; no automatic retry is authorized.

This review can complete worker conformance only. Native-catalog retrieval
telemetry, the workbook pilot, main campaign allowance and all product acceptance
stages remain separate. The prior four request IDs are terminal and cannot replay.

Conformance records bind the exact checked executor settings. Task routes with
different instructions, invocation modes or other identity-bearing settings still
need matching identity evidence and approval. This scope does not authorize a
workbook pilot or turn bootstrap observations into task-performance evidence.
