# AEEP 0.5 live DeepSeek Harness comparison

The fair measured run used six fresh, read-only sessions on DeepSeek-V4-Flash
with low reasoning: three direct counting tasks and three identical tasks routed
through AEEP's deterministic `text.stats` capability. Three earlier pilot
sessions were excluded because their prompts disclosed the expected answers.

| Arm | Correct | Model calls | Tool calls | Total provider tokens |
|---|---:|---:|---:|---:|
| Direct model | 2/3 | 3 | 0 | 34,732 |
| AEEP routed | 3/3 | 6 | 3 | 71,114 |

AEEP improved correctness for this deliberately simple deterministic task, but
it did **not** save tokens. It used 36,382 more tokens, or 104.7507% overhead,
because each tool call required a second model step and another copy of the DSH
system/tool context. This is a measured negative result, not a release failure:
the safety gates require truthful accounting, not a flattering threshold.

The earlier approved plugin proof discovered the community
`dsh.coding-tools.read-file@1` capability and selected its qualified MCP route.
AEEP had usable latency/network estimates for ranking. Its plugin token fields
were zero/unavailable, so the system did not pretend to have a provider token
estimate it had not measured. All 18 imported community candidates remain
suspended after the proof, and the DSH server remains running.
