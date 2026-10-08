# Evidence, measurement, reporting and product acceptance contract

## Primary scientific question

Does *optional access* to candidate version X improve an already-capable agent on task family Y under the same model, harness, existing tools, exposure policy, validation and budget? Distinguish this from forced-use qualification, which only asks whether a skill can work when invoked.

### Study design

- **Control:** Same ordinary model/host, baseline tools, settings, workspace fixtures and independent verifier, without the candidate. Keep ordinary competing tools.
- **Treatment:** Identical normal environment with candidate available (not forced); verify candidate tool definition/skill exposure separately, and whether it was used.
- Pre-register tasks and outcomes; include tiny/easy, complex, and unrelated/negative-control tasks; source independent/held-out variations (developer-authored cases aren't sufficient alone). Freeze grader/version, budget, models, random seeds, order, and thresholds before holdout.
- Run multiple paired trials with isolated/reset workspaces and controlled workers per existing AEEP security policy; record shared resources, session leakage, caching/warm-ups, tool collisions, inter-run carryover and effective catalogs.
- Unit/integration/replay tests can qualify *software plumbing*, never live plugin effectiveness. Unreviewed or leaking workers cannot support strict comparative evidence.
- Explicit approval required for live calls, credentials, third-party effects, model fees and external services. Tests must stop when budget/authority is exhausted.

### Required measurements (per-arm, per-task, per-trial)

1. Candidate/version/behavior digest; agent host/version, model/effort/region or tier where applicable; existing capabilities and effective exposure; task family, fixture and verifier digests.
2. Output verification: pass/fail/skipped/unknown with independently checked artifacts; execution errors, retries, interventions and candidate invocation.
3. Provider-reported input/output/cached/reasoning tokens with exact field semantics. Don't assume cached or reasoning tokens are additive to the reported total; preserve raw observations and a source-defined accounting model.
4. `agent_wall_seconds` measured from entry to terminal result; `verification_wall_seconds` separately; `setup_wall_seconds` separately. Say whether plugin discovery/tool-selection overhead is included. If time to verified success is reported, include verification but identify its cost.
5. Actual provider-billed cash, published-rate estimate or unavailable; plugin subscription/usage charges; local compute and evaluator costs separately. Never convert subscription quota into cash savings without a credible causal billed amount.
6. Worker image/host version and containment checks. An apparent 'disabled skill' is not proof that its files, definitions or learned context weren't visible.

### Calculations

- Mean token/time change for the exact matched cohort: `mean(control) - mean(treatment)`; positive = resource saving. If control mean > 0, relative saving = difference/control mean. Negative = treatment consumes more. Also report medians and spread/paired uncertainty where sample allows; highlight outliers and low N.
- Success delta = treatment verified-success rate minus control verified-success rate (percentage points), with sample size and interval/suitable uncertainty. Never allow token savings to override substantial quality regression as a favorable overall recommendation.
- Cost per verified success = **sum of relevant consumed task-run costs including failures and retries** / **number of verified successes**. Undefined when there are zero successes or unavailable price coverage; don't omit costly failures. Report grader/benchmark overhead separately, not as a pretend user task savings. For recurring deployment, disclose amortization assumptions.
- A plugin's subscription breakeven requires observed or defensibly estimated *real marginal cash savings* per equivalent successful task and a real price. If price or billability unknown, show 'break-even unavailable'. For a user with fixed subscription, fewer tokens may give capacity/performance benefits without reducing cash billed.
- Attribute measured difference to **access to the candidate under tested conditions**, not necessarily its invocation or causal contribution to every success. Carry uncertainty when candidate wasn't invoked or other interactions changed.
- If tool-call usage is unreported, show unknown; don't count it as zero. Report measurement coverage (N reported / N runs).

### Outcome categories

`DEMONSTRATED_BENEFIT` (quality noninferiority and supported meaningful benefit), `DEMONSTRATED_REGRESSION`, `NO_DEMONSTRATED_MATERIAL_DIFFERENCE`, `INCONCLUSIVE`, `NOT_ASSESSED`/`BLOCKED`.

Do not make 'DEMONSTRATED_BENEFIT' automatic based only on a positive point estimate. State the predeclared thresholds, uncertainty, sample size, evidence authority and version applicability. Development tests may return `INCONCLUSIVE` correctly.

### Report content required

- Candidate name, repository/source/version/digest, developer identity evidence, test period.
- Plain-language task family verdicts, where it helps or hurts, scope and limitations.
- Baseline definition and agent/model/version, candidate availability vs actual use.
- For each comparable task: verified success comparison, tokens by category/source, wall-clock, failures/retries, real/estimated/unknown cash, N, uncertainty and limitations.
- User workload assumptions and break-even only where calculable.
- Permission/storage/privacy footprint, installation state and optional developer support/purchase link.
- Clear labels distinguishing reproducible independent tests vs developer claims, partial compatibility, synthetic fixture, real host, historical/outdated evidence.
- Default private output; publishing is separate explicit action, removing sensitive prompts/files and authentication artifacts.

### Product behavior examples that MUST pass tests

1. Both arms pass a trivial edit and treatment costs more -> not beneficial simply because it invoked a skill.
2. Treatment fails more often but saves tokens -> regression/inconclusive, not positive.
3. Treatment wins complex edits but loses easy edits -> separate task-family conclusions.
4. No provider cash is available -> `null`/unavailable, not `$0`.
5. Token categories overlap -> no naive summation.
6. Subscriptions only -> no billed-cash reduction claim.
7. One pair favors candidate -> directional/inconclusive, no statistically significant claim.
8. Different model version, effective tool catalog or worker image -> not pooled into a comparable cohort.
9. Unknown evaluator/grader output -> skipped or inconclusive, not silently scored fail/pass.
10. Fixed monthly plugin price and measured per-task economic benefit -> disclosed break-even with usage assumptions, never automatic payment.
11. Plugin code changes/updates -> prior evidence stale until applicability rechecked.
12. Native agent functionality already solves task -> system can recommend **no plugin**.
13. Benchmark runner claims completed while timeout leaves uncertain side effects -> stop/reconcile; never blindly repeat a consequence.
14. Installer selects an incompatible/nonfree extension -> preview blocked, no partial silent install.

## Public release evidence gates

Software tests, installer/source builds, host conformance, real paired experiments, human-comprehension results and independently reproduced claims are separate gates. Maintain explicit statuses. A polished website is not evaluation evidence. Never publish claims with metrics that were computed from a fake/replay harness as if they were live.
