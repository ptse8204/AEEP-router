# PostgreSQL reference tasks passed in both MCP packs

Each original seed ran in its own PostgreSQL fixture. The protected
verifiers rejected missing outputs. AEEP invoked the pinned server's
real `execute_sql` tool over MCP stdio, and both original verifiers then
accepted the resulting database state.

| Pack | Missing output | Reference | New operations | Charged elapsed |
| --- | --- | --- | --- | --- |
| [MCPMark](../mcpmark-postgres-tool-schema-20261105/execution/summary.json) | 0 | 1 | 25 | 6.845 s |
| [MCP-Universe](../mcp-universe-postgres-tool-schema-20261105/execution/summary.json) | 0 | 1 | 28 | 6.568 s |

Both approved runs used the retained PostgreSQL 17.11 and Postgres MCP
0.3.0 images and independent loopback-only database namespaces. A
read-only audit matched 51 receipts to the canonical database, verified
53 settled operations, and found all ten retained containers exited.
Stopping the databases released their temporary state. Prior charges
remain, including MCPMark's older charged reservation with unknown
measured latency. Zero model turns and $0 cash were charged for the new
runs. The elapsed figures are charged engineering intervals.

MCPMark binds revision `cd45b7f57923`. MCP-Universe binds
`0df6c42717f2`. They share the reviewed SQL transaction and tool schema.
Their original seed and verifier bytes remain separately bound. The
[linked evidence](results.json) proves a local reference journey for
each pack on the pinned coordinator. It does not complete ordinary CLI
composition, measure comparative usefulness, or qualify the packs for
broader tasks. Comparisons remain paused.
