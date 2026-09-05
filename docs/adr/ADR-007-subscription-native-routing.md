# ADR-007: Subscription-native routing

Status: accepted for AEEP 0.7.

## Decision

`ActionRequest` remains the exact, versioned semantic boundary. A planner or
native Tool Search discovers the capability; AEEP applies local feasibility and
economic policy to its already-qualified implementations. Legacy `host` remains
delegated. A distinct `host_managed` executor calls a reviewed adapter directly.
The Codex App Server is the first adapter, but the router core depends only on
the provider-neutral managed-host protocol. Codex retains authentication and
AEEP never reads, copies, returns, or stores reusable authentication material.

## Rejected alternatives

- Rebuild generic MCP/tool discovery in AEEP: rejected because it duplicates the
  host, expands model context, and turns the router into a planner.
- Change `host` to direct execution: rejected because it would silently alter
  established delegated behavior and external-outcome receipts.
- Call an OpenAI API directly: rejected because it bypasses the user's managed
  subscription and would make the core provider-specific.
- Scrape CLI JSONL or authentication files: rejected because the App Server has
  a distinct protocol and Codex must remain the credential owner.

## Consequences

Managed routes need explicit local adapter configuration and a second approval
intersection. AEEP may execute one bounded host turn and record sanitized usage,
but it neither plans the action nor owns login state. Older host integrations
continue unchanged.
