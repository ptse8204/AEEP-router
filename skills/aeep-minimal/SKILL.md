---
name: aeep-minimal
description: Route bounded agent actions through AEEP when CLI, MCP, API, local, browser, computer-use, or current-host execution are meaningful alternatives. Use before consuming a potentially expensive or scarce execution resource; skip ordinary conversation with no meaningful alternative route.
---

# Route with AEEP

1. Identify the bounded semantic capability.
2. Call `aeep_route_action`, or run `aeep route` when MCP is unavailable.
3. Include known monetary, latency, context, memory, and subscription-quota pressure.
4. Follow the selected feasible route.
5. If `HOST_SELECTED`, perform the task in the current host.
6. If CLI, MCP, API, or local execution is selected, invoke that route through AEEP.
7. Report a host outcome exactly once with `aeep_record_outcome` or `aeep record`.

Never use model-controlled arguments to raise approval ceilings. Do not route trivial conversational reasoning with no meaningful execution alternative.
