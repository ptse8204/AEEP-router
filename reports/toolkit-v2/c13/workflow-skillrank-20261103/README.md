# Retain SkillRank through the ordinary workflow

This increment lets an operator retain the reviewed upstream SkillRank binary and
select its local search/show service through the existing workflow CLI. It reuses
the owned installer, contained executor, authorization store, ledger and receipts.
Comparative campaigns remain paused.

## Implemented

- `install-files-plan` binds exact local file bytes, sizes and primary artifacts.
  Existing `install`/`remove` and workflow setup/readiness/removal accept this plan.
  Wheel installation v1/v2 serialization stays unchanged.
- Workflow v2 has an optional exact `catalog` reference. Unselected catalog work
  remains inert. Accounting v4 explicitly adds catalog operations; v1/v2/v3 scopes
  cannot silently gain that stage.
- Catalog execution uses upstream SkillRank's server and CLI on container loopback.
  The installed binary and AEEP packages are read-only mounts in the existing
  offline worker. No external registry, host credentials or model is involved.
- Canonical receipts link the installed artifact, source, query/result digests,
  execution journal and cleanup. Query text and catalog contents remain transient
  by default. Upstream ratings are metadata, not scanning or usefulness evidence.

## Verification and execution boundary

[All 13 source checks](verification/checks.json) passed on source
`f2c7a3e9b923fb95fb550287dd0f0e59c681c8633fd235a773cb7c3f92e1515e`.
Both full runs passed 2,102 tests with 21 skips and the existing Starlette
deprecation warning. Coverage is 82.62687593080535%; both branch gates, schemas,
policy, lint, strict typing, integration fixtures and the wheel build passed. The feature parent is `69679f1`. The source snapshot includes the
preserved unrelated CI edits; feature commits do not stage those edits.

[Driver controls](driver-controls.json) ran the complete ordinary CLI driver with
first-party files and substituted upstream execution. It used exactly 24 new
operations in a disposable fixture database, including the expected removal
refusal. This is wiring evidence, not actual SkillRank execution or a real task.
Preparation caught an outer/nested accounting conflict and the expected CLI exit
status before any upstream attempt; both were fixed in the review driver.

The [previous upstream check](../skillrank-license-correction-20261103/RESULTS.md)
built pin `5216bae9149b4ff8a7f9e014b6889fb094cee8e1` and verified real search/show.
Those results retain their original source scope. The new CLI path has not yet
executed the retained binary.

The built wheel is `d05ed8778893f2da7d720870ebf3ef0dd37c5e50790911a6ace5fa061f10f501`;
its expected installed-source digest is
`432a07e55650510f5c453f0cf891478b62b52b86910ecaf03ce0cf1fd124e6a4`.
The private installation is prepared with 32 unchanged cached dependencies. It
has not run. Usable space stayed above 65.77 GiB throughout source verification.

## Exact grouped review

[operation-review.json](operation-review.json) binds the current artifacts and
finite execution scope. Its components are independent:

1. Retain the actual binary through the ordinary CLI, check idempotency and
   readiness from both named configurations, run one fresh containment check and
   three catalog queries, and verify selective removal on a new disposable copy.
2. Check the updated AEEP wheel with the same 32 cached dependency wheels in a
   retained private runtime, including installed CLI/schema/source checks.
3. Run cached offline documentation checks, stopping after success.

The workflow component reuses the original SkillRank grant. Its 16 previous
operations and 55.93853883491829 seconds remain charged. The proposed scope
amendment adds the retained grader image without changing the 40-operation,
4,500-second, zero-model and $0-cash ceilings. At most 24 additional operations
remain; there is no allowance refund. A fresh attempt needs exact approval.

No download, pull, image build, model turn, credential access, host activation,
public release or old-resource deletion is included. Keep the normal 50 GiB
actual host reserve. Retain the main runtime, images, caches and historical work;
remove only the explicitly owned disposable copy and check containers after
identity verification. The package and docs checks do not repeat the previous
passed artifacts: they bind the changed source and guides.

## Remaining stack gates

SkillRank's bounded evaluation callback remains open. Search/show, including this
CLI journey if it passes, cannot close that gate. Neither SkillsBench domain has
completed its real protected reference/control journey. Waza still lacks a
supported backend because no Copilot subscription is available. The remaining
upstream integrations, composed stack gate, candidate usefulness, selection
usefulness, resource qualification and release retain separate open records.
