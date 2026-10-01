# Native-catalog observation gap

Checked September 24, 2026 against the [official App Server documentation](https://learn.chatgpt.com/docs/app-server) and the locally generated 0.154.0 schema.

| Observation | Established | Limit |
| --- | --- | --- |
| Skill inventory | `skills/list` is documented | Listing a skill does not establish that a trial retrieved its instructions |
| Tool invocation | Completed command/MCP/dynamic-tool items are documented | An invocation does not establish the discovery path |
| Raw tool-search items | Present in the installed generated schema | No complete supported retrieval-event contract was established from the public documentation |
| Sandbox inspection | `command/exec` is documented without a thread/turn | Supporting boundary evidence only; it cannot satisfy catalog evidence |

Keep exposure, retrieval and invocation unknown unless their corresponding observations exist. Do not infer “not retrieved” from a missing event or replace native discovery with a custom catalog.

To close this gate, establish a supported event contract for the pinned version, verify positive and negative retrieval cases in an authorized conformance run, preserve normalized identifiers without task contents, and test dropped/incomplete events. Then run the frozen native-catalog campaign. This work remains separate from valid marginal-value evidence.

The [schema review record](catalog-observation-review.json) records the inspected schema digest. It is documentation research, not a live conformance record.
