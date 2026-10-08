# AEEP documentation

AEEP aims to help your agent find useful capabilities and put approved ones to
work, with less manual tool selection and limits you control. These guides take
you from connecting an agent to evaluating tools and running approved work.

Start with [setup](ONBOARDING.md). Once connected, search for capabilities,
review what they need and choose your next step below.

## Tutorials

Try the workflow on a small task before configuring your own tools.

| Try | Result |
|---|---|
| [Connect an agent](ONBOARDING.md#start) | Configure Codex, Claude Code, DeepSeek Harness or an API application, then check setup. |
| [Local text action](../examples/quickstart/README.md) | Preview a route, execute a deterministic action and inspect its receipt. |
| [Terminal walkthrough](media/README.md) | Follow the recorded CLI commands and three synthetic stack examples. |
| [Offline stacks](STACK_PLANNING.md#try-the-offline-journey) | Compose media, data and research fixtures with explicit verification limits. |

## How-to guides

Choose the part of your workflow you want to set up or change.

| Task | Guide |
|---|---|
| Search catalogs, configure components, control access, update or disconnect | [Onboarding and controls](ONBOARDING.md) |
| Connect a host or integrate an application loop | [Agent integrations](INTEGRATIONS.md) |
| Review a candidate and compare it with existing tools | [Assessment](ASSESSMENT.md) |
| Operate a scoped project tool | [Project-local tasks](ASSESSMENT.md#project-local-task-operation) |
| Plan and execute an approved stack | [Stack planning](STACK_PLANNING.md) |
| Configure a subscription-backed route | [Bring your own subscription](BYOS.md) |
| Operate economic evidence and recover unresolved attempts | [Economic operator guide](ECONOMIC_OPERATOR_GUIDE.md) |
| Implement a provider's quote and usage handlers | [Provider integration](PROVIDER_INTEGRATION.md) |
| Prepare controlled assessment workers | [Managed-worker contract](../integrations/managed-worker/README.md) |
| Define and run assessment checks | [Assessment testing policy](ASSESSMENT_TESTING.md) |

### Integration and example recipes

Run examples from the repository root after source installation. Each recipe
states whether it uses local fixtures, network access or separately approved
model execution. Check a retained report with `--check` when that option exists;
regenerating reports is a different operation.

- [Python embedding and local routing](../examples/quickstart/README.md)
- [HTTP executor](../examples/http/README.md) and [stdio MCP executor](../examples/mcp/README.md)
- [GitHub default branch](../examples/github/README.md)
- [Subscription routing and Codex diagnostics](../examples/subscriptions/README.md)
- [Scoped native website fixture](../examples/native_website/README.md)
- [Provider-package lifecycle](../examples/provider_package/README.md)
- [Local economic service](../examples/economic_market/README.md) and [economic proof](../examples/economic_evidence/README.md)
- [DSH campaign checks](../examples/dsh_campaign/README.md) and [job-application sandbox](../examples/job_application/README.md)
- [Controlled proof assets](../examples/proof/README.md)
- [Codex plugin launcher](../integrations/aeep/README.md) and [DSH native bridge](../integrations/dsh-aeep-router/README.md)
- [Connection-bound API example](../examples/deepseek_connection.py)

## Reference

Use these contracts when building an integration or checking exact behavior.

- [Protocol specification](../SPEC.md) and [ActionRequest schema](../schemas/action-request.schema.json)
- [Economic accounting](ACCOUNTING.md)
- [Provider packages](PROVIDER_PACKAGES.md), [provider trust](PROVIDER_TRUST.md) and [portable evidence reuse](EVIDENCE_REUSE.md)
- [Cache affinity](CACHE_AFFINITY.md) and [offline x402 capacity binding](protocol/X402_CAPACITY_BINDING.md)
- [Security policy](../SECURITY.md) and [threat model](THREAT_MODEL.md)
- [Architecture decisions](adr/ADR-007-subscription-native-routing.md): [capacity](adr/ADR-008-capacity-transferability.md), [x402](adr/ADR-009-x402-compatibility-boundary.md), [ARD discovery](adr/ADR-010-ard-discovery-boundary.md), [stack preflight](adr/ADR-011-stack-synthesis-preflight.md)

### Version-specific compatibility

Subsystem and wire versions have their own meanings. A 0.5 or 0.6 guide can
describe a contract still supported by AEEP 0.8; do not treat its title as an
installation recommendation. For an existing database or package, read the
applicable transition and back up before upgrading:

- [Migration to 0.4](MIGRATION_0.4.md)
- [Migration to 0.5](MIGRATION_0.5.md)
- [Migration to 0.6](MIGRATION_0.6.md)
- [Migration to 0.7](MIGRATION_0.7.md)

## Explanations and evidence

Understand the design choices and the results behind them.

- [Architecture and design decisions](../ARCHITECTURE.md)
- [Tests, useful cases and known limits](EVIDENCE.md)
- [Economic evidence exchange](ECONOMIC_NETWORK.md)
- [DSH validation method](DSH_VALIDATION.md)
- [Job-application sandbox design](JOB_APPLICATION_DEMO.md)

Each measured result applies to its recorded source, environment and task.
The completed DOCX and composed workbook studies did not qualify their
candidates. The normal-agent / discovery-only / discovery-plus-AEEP comparison
remains unrun, and human comprehension remains unmeasured.

## Contributors and historical work

Use [Contributing](../CONTRIBUTING.md) for development and local documentation
checks, and [AGENTS.md](../AGENTS.md) for repository instructions. The
[code of conduct](../CODE_OF_CONDUCT.md) applies to participation.

[Plan coverage](../reports/v08/plan-coverage.md) is the implementation and
remaining-gate record. The [0.8 evidence index](../reports/v08/README.md) and
[changelog](../CHANGELOG.md) retain earlier results. The [0.7 roadmap](ROADMAP_0.7.md)
and [0.7 upgrade status](upgrade/STATUS.md) are historical records, not current
release promises. Adopted ADRs and historical reports keep their original bytes.
