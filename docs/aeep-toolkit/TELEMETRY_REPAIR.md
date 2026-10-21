# Check token capture and candidate loading

Managed reports now show whether retained token counts match their execution
journals. This helps distinguish a missing counter from a counter whose provider
has not independently attested its accuracy. Neither condition is a measured zero.

The [retrospective capture audit](../../reports/toolkit-v2/c07/capture-repair-20261019/capture-audit.md)
verified all 564 captures in the completed editing comparison. It read the original
attempt stores without dispatching workers or models. The supplement exports the
journals and receipts needed to reproduce its consistency checks. The original
report, frozen utility policy and inconclusive outcome are unchanged.

## What the report verifies

For each normalized primary run, the managed bridge resolves the original journal
and checks its digest, attempt, runtime and boundary against the retained receipt.
It compares the final cumulative token accounting, observed wire fields and raw
resource counts. Complete terminal captures receive `status: verified`; partial
and unavailable captures retain their own states. Conflicts become normalization
gaps. `managed-evidence.json` includes the checked journals and per-run results;
HTML, Markdown and JSON summaries show capture coverage.

The counts retain `provider_report/self_asserted` provenance. Capture verification
does not change those labels or make the strict token utility gate pass. Descriptive
comparisons of reported counts remain available. Using those counts for a formal
admission decision would require a separately reviewed evidence-policy change.

## What candidate loading means

The completed study had `catalog_metrics` disabled. Its receipts cannot establish
whether Ponytail instructions were loaded or influenced an answer. No retrospective
analysis can recover events that were never retained.

Prospective reviewed workers can enable the existing `catalog_metrics` option.
This requires the exact collector file in the immutable worker. The collector
uses one worker-local loopback OTLP endpoint, disables prompt logging and trace
export, and retains bounded numeric observations and hashed skill names. It adds
no hosted telemetry service or package dependency.

The adapter records the resolved candidate name hash and reviewed content hash.
The router now retains the validated snapshot and its scope. The managed bridge
accepts a positive `codex.skill.injected` event only when the candidate digest
matches the frozen mapping and the snapshot matches the same execution journal.
The report calls this `instructions_loaded: true`. Ambiguous candidate names,
missing events and failed exports remain unknown. Loading instructions does not
prove semantic use, invocation of a separate tool, or causal benefit. Existing
`candidate_invoked` and admission semantics remain unchanged.

Codex 0.154.0 can lose metrics on exporter failure or forced termination, even
when the process exits successfully. Collector shutdown therefore never proves
delivery completeness or candidate non-use. The retained
[native telemetry investigation](../../reports/v08/native-catalog-telemetry-review.md)
documents those failures. Current
[App Server documentation](https://learn.chatgpt.com/docs/app-server)
describes token-usage notifications and tool item events; that documentation does
not qualify a different installed version.

## Remaining review

A new collector profile changes the effective worker telemetry policy and starts
a local listener. Review its exact images, source, denied-access probes, synthetic
inputs and finite model allowance before execution. Start with a small diagnostic;
keep optional-use checks separate from forced invocation. A successful diagnostic
cannot repair the old campaign's missing candidate-use evidence or justify a new
efficacy claim.

### October 20 execution status

The approved wheel and 67-file offline documentation checks passed. The first
collector inspection failed before Codex initialized: both pinned images contain
collector bb758886…, whereas their reviewed-file guard requires d551e2f4….
No diagnostic model turn ran. The old comparison remains unchanged.

[The prepared correction](../../reports/toolkit-v2/c07/capture-image-repair-20261020/README.md)
replaces only that file in two COPY-only image layers, then requires fresh
conformance before the maximum four public capture tasks. It needs explicit
approval because the preceding exact review excluded builds and replay. The
existing OTLP implementation and package pins are unchanged; no hosted backend
or authentication intervention is needed to correct these image bytes.
