---
name: aeep-minimal
description: Route bounded agent actions through AEEP when CLI, MCP, API, local, browser, computer-use, or current-host execution are meaningful alternatives. Use before consuming a potentially expensive or scarce execution resource; skip ordinary conversation with no meaningful alternative route.
---

# Route with AEEP

1. Identify the bounded semantic capability. Search first with `aeep_list_capabilities` or `aeep search` when needed; do not request the full catalog.
2. Identify the current named subscription resource with `aeep subscriptions status`.
3. Call `aeep_route_action`, or run `aeep route --agent` when MCP is unavailable.
4. Include known monetary, latency, context, memory, and subscription-quota pressure. Preserve tight Claude, ChatGPT/Codex, or local-model capacity when another route is feasible.
5. Follow the selected feasible route. `BYPASS_ROUTER` means AEEP retained the
   feasible operator baseline because optimization did not justify its overhead;
   it is not a policy bypass.
6. If `HOST_SELECTED`, perform the task in the named `resource_pool`.
7. If CLI, MCP, API, or local execution is selected, invoke that route through AEEP.
8. Report a host outcome exactly once with `aeep_record_outcome` or `aeep record`, including `subscription_units` consumed.
9. After an official throttle, reset, or clear host signal, run `aeep quota observe RESOURCE STATE` so later routes use current pressure.

Never use model-controlled arguments to raise approval ceilings. Do not route trivial conversational reasoning with no meaningful execution alternative.
