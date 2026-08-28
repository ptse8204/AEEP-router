# AEEP 0.6 proof assets

These assets preserve the qualification, accounting, campaign, workflow, and
release-gate paths introduced before 0.4. The `fixture.*` routes are hermetic
harness tests and must never be described as live model evidence. The 0.4
economic-settlement campaign is documented separately under
`examples/economic_evidence/`.

The controlled MCP supply is the Docker `fetch` image pinned in
`docker-fetch-provider.json`. The operator profile is named `aeep-lab`, has
dynamic tools disabled, and enables only `fetch.fetch`. Qualification is bound
to the checked-in image/profile/gateway fingerprint before activation.

Campaign outputs belong in `.aeep/proof-results/`; the isolated benchmark
database belongs in `.aeep/`. Neither contains action inputs or model outputs.
Direct API campaigns remain cost-gated: do not run them without an explicit
cash ceiling and per-trial billing evidence. Subscription-backed Codex
campaigns may report measured tokens and API-equivalent counterfactuals, but
actual cash and subscription credits remain unavailable without independent
evidence.

`openai-gpt-5.6-sol-standard-rate-card.json` pins the official standard API
tariff retrieved on 2026-08-14. Subscription-backed Codex token usage may be
valued against it with `aeep campaign revalue`; the result is API-equivalent
counterfactual evidence, never actual cash. Cache reads and cache writes are
metered separately and removed from uncached input before pricing.

`github-workflow-suite.yaml` is the controlled live workflow campaign. It
compares the direct GitHub REST route with the activated Docker MCP fetch plus
local parser DAG and accounts for both workflow leaves on every trial.

## Controlled Docker setup

Docker Desktop 4.84.0 / Docker 29.6.2 and MCP CLI 0.43.3 were used for the
checked-in descriptor. Recreate and inspect the profile before using it:

```bash
docker mcp feature disable dynamic-tools
docker mcp profile create aeep-lab
docker mcp profile tools aeep-lab --disable-all fetch
docker mcp profile tools aeep-lab --enable fetch.fetch
docker mcp profile show aeep-lab
docker mcp gateway run --profile aeep-lab --verify-signatures
```

The expected `mcp/fetch` OCI digest is
`sha256:1a7a0996a565a0b8ca5c41b42830d4e5f334d33f851596bbd9debb2beedb22d3`.
Any image, tool schema, gateway, argv, or profile drift requires a new
descriptor, qualification, and activation.

```bash
aeep candidate ingest @examples/proof/docker-fetch-provider.json \
  --source-id docker:aeep-lab:fetch \
  --capability web.fetch@1 \
  --manifest examples/proof/aeep.yaml
aeep candidate qualify docker.aeep-lab.mcp.fetch \
  --side-effect read --idempotent --safe-to-auto-execute \
  --cases @examples/proof/docker-fetch-qualification.yaml \
  --repetitions 3 --conditions process-cold,router-warm \
  --manifest examples/proof/aeep.yaml
aeep candidate activate docker.aeep-lab.mcp.fetch \
  --manifest examples/proof/aeep.yaml
```

## Campaigns and current evidence

```bash
aeep campaign run @examples/proof/github-workflow-suite.yaml \
  --manifest examples/proof/aeep.yaml \
  --database examples/proof/.aeep/github-workflow.db \
  --output examples/proof/.aeep/proof-results/github-workflow.json
aeep workflow run @examples/proof/github-mcp-workflow.yaml \
  --manifest examples/proof/aeep.yaml
```

The controlled public GitHub campaign completed 20/20 direct HTTP and 20/20
Docker-MCP-plus-local workflow trials in both requested conditions. The router
correctly froze the direct HTTP route for holdout: the hybrid was materially
slower for this small fetch. MCP cache telemetry confirmed 19/20 reused-router
measurements as actual cache hits; the miss remains in the raw report and is
excluded from warm statistics. Cash remained unavailable because static zero
estimates are not actual-cash evidence.

The live subscription-backed Codex campaigns are `local-data-codex-live-suite.yaml`
and `github-codex-live-suite.yaml`. Each completed 20/20 valid trials in both
conditions. The full agent used a median 17,921 input tokens in local-data and
about 36,000 in GitHub; the deterministic routes used no model tokens. Median
API-equivalent values under the pinned official snapshot were approximately
$0.0468 per local-data trial and $0.0525-$0.0616 per GitHub trial. Actual cash
and Codex-credit consumption remain unavailable, not zero.

`local-data-codex-terra-medium-suite.yaml` is the current host-portability
comparison. It pins Codex CLI 0.147.0 to `gpt-5.6-terra` with medium reasoning
and runs ten randomized direct/AEEP pairs in both process-cold and router-warm
conditions. All 40 measured trials passed the exact oracle and receipt gates.
The 20 direct turns used 287,104 provider tokens; AEEP routed the same actions
to the exact-compatible local implementation without a model call. See the
[campaign report](../../reports/v06/codex/campaign.md) for the bounded claim,
bootstrap interval, raw-resource split, and excluded setup usage.

```bash
aeep campaign run @examples/proof/local-data-codex-live-suite.yaml \
  --manifest examples/proof/aeep.yaml \
  --database .aeep/live-codex-local-data.db \
  --output .aeep/proof-results/live-codex-local-data.json
aeep campaign run @examples/proof/github-codex-live-suite.yaml \
  --manifest examples/proof/aeep.yaml \
  --database .aeep/live-codex-github.db \
  --output .aeep/proof-results/live-codex-github.json
aeep campaign run @examples/proof/local-data-codex-terra-medium-suite.yaml \
  --manifest examples/proof/aeep.yaml \
  --database .aeep/codex-terra-medium-comparison.db \
  --output reports/v06/codex/campaign.json
aeep campaign prove \
  --report-file .aeep/proof-results/live-codex-local-data.json \
  --report-file .aeep/proof-results/live-codex-github.json \
  --baseline-route full-agent --hybrid-route hybrid \
  --output .aeep/proof-results/live-codex-release-proof.json
```

The locked correctness, token, time, policy-oracle, activation, and ledger
separation gates pass for these two campaigns. This is not an actual-cash claim
and does not replace a separately authorized API-key campaign.
`aeep campaign prove` writes the requested proof artifact and exits with status
4 when any locked gate fails, so CI must inspect the command status as well as
retain the report.
