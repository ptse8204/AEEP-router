# Combined protected-worker review

Status: **approved and executed once on September 25, 2026**. See [approval](paired-conformance-approval.json) and [validated results](paired-conformance-live-result.md). The original JSON bundle remains unchanged.

| Item | Exact bound |
| --- | --- |
| Grant | Existing `onboarding`; counters and ceilings retained |
| Additional operations | Four: two connectivity calls and two paired inspections |
| Model turns | At most two, one per connectivity call; no candidate task |
| Reserved elapsed allowance | At most 610 seconds combined |
| Model/settings | `gpt-6-astra`, medium reasoning, pinned Codex 0.154.0 |
| Images | Existing capable control and Spreadsheets treatment images |
| Credentials | Existing separate protected volumes; no new login or credential-file reads |
| Local writes | Private synthetic workspace files, exact synthetic canaries and cleanup |
| Cash/disclosure | Zero cash; disclosure restrictions unchanged |
| Current ledger | 308 operations, four reserved turn allowances, 279.38554054975975 seconds; cash zero |
| Remaining before this bundle | 296 turn allowances and 3320.61445945024 seconds |
| Expiry | 2026-09-26T13:35:23.682424+00:00 |

Bundle SHA-256: `6f107f5d13045a69cab3f25184a754a52fa64803de45ada18cfd980cf334917c`.

[Exact definitions and immutable scope amendment](paired-conformance-review-bundle.json).

The two connectivity prompts return only a fixed connection result. They do not
send plugin content or execute candidate tasks. The paired inspection uses fixed
commands for policy, shared libraries, candidate dependencies and absence in
control, synthetic cross-worker/answer/credential canaries, command-network denial,
resource limits and worker interruption. It makes no model turns. Elapsed charging
sums the two measured worker-operation lifetimes, including synchronization.

The treatment worker adds an explicit pin for its existing skill file; image,
network, credential volume and resource limits stay as listed in the definitions.
Both routes now pin the observed model, reasoning level and protocol user agent.
Failed or interrupted requests retain evidence and charges and are never blindly
replayed. This does not authorize a benchmark campaign, budget expansion,
admission, or an automatic declaration of full conformance. Effective policy,
enforcement review and source-bound probe validation remain required afterward.

Approval is required because the assessment policy binds reviews to exact
definitions. Earlier sign-in/connectivity approval and superseded narrow
inspection questions do not approve this changed runtime and scope.
