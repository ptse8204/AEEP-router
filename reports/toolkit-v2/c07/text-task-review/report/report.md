````text
AEEP evidence summary

Value verdict: NOT_ASSESSED

Descriptive records only. Unknown is not zero; fewer resources do not establish benefit.

Candidate source: "https://github.com/DietrichGebert/ponytail"
Revision: 1d95ff7d39de12d87014ea40d4e22201bddc501b; payload SHA-256: 28db736a30751c76ae4f8649e5f810ae086213f7e15ad601e692b6f87188117e
Source metadata is supplied provenance, not verified developer ownership.

Canonical managed assessment
Recorded outcome: insufficient_evidence; qualification passed: False.
Analysis: 62976a077973791f7dbd10ee453b4677432f7e961ad21caeebf9d0cdeb107b60; campaign: 2dc8c66fcb41e61c1486138a6f13b72978dde19dfe2dd2b0ac2ec5eff20e04bd; operation ledger: a9d866ff945e38fcbae06df830a713961eaca4c7a801290f59500103ada7cf63.
Distinct holdouts: 0; distinct paired cases: 0.
Correctness failures: 0; execution failures: 1.
Expected trial positions: 141; missing: 140; unexpected: 0; duplicate: 0.
Unresolved operations: 0.
Trial wall time includes routing and preflight; separately measured grading is excluded by BenchmarkRunner.
Positive paired resource differences mean control used more. Success gains use treatment minus control. Intervals and guardrails retain the frozen analysis policy.
Paired measurement coverage: {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}
Paired resource differences: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Uncertainty intervals: {}
Separate worker conditions: {"fresh-worker": {"break_even_uses": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "paired_measurement_cases": {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}, "paired_savings": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "savings_interval": {}}}
Utility, guardrails and challengers: {"analysis": "all_assigned_cases", "benefit": false, "candidate_selection_filter": false, "challengers": {}, "complete": false, "dominated": false, "family_error_rate": 0.05, "guardrails_passed": false, "metrics": {"input_tokens": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}, "output_tokens": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}, "task_success": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}, "wall_time_ms": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}}, "stage": "qualification"}
Assessment usage, including known subtotals: {"assessment_total.local.cpu_ms": null, "assessment_total.local.gpu_ms": null, "assessment_total.local.memory_mb_seconds": null, "assessment_total.local.network_bytes": null, "assessment_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "assessment_total.subscription.openai.codex.self.provider_unit": null, "assessment_wall_time_ms": 126082.53299957141, "campaign_total.local.cpu_ms": null, "campaign_total.local.gpu_ms": null, "campaign_total.local.memory_mb_seconds": null, "campaign_total.local.network_bytes": null, "campaign_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "campaign_total.subscription.openai.codex.self.provider_unit": null, "campaign_wall_time_ms": 5143.953708931804, "included_invocation_guard_ms": 96.24129300937057, "included_routing_overhead_ms": 4.883582936599851, "known_campaign_subtotal.local.cpu_ms": null, "known_campaign_subtotal.local.gpu_ms": null, "known_campaign_subtotal.local.memory_mb_seconds": null, "known_campaign_subtotal.local.network_bytes": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_campaign_subtotal.subscription.openai.codex.self.provider_unit": null, "known_campaign_wall_time_ms": 5143.953708931804, "known_overhead_subtotal.local.cpu_ms": 467.4980000000001, "known_overhead_subtotal.local.gpu_ms": null, "known_overhead_subtotal.local.memory_mb_seconds": null, "known_overhead_subtotal.local.network_bytes": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_overhead_subtotal.subscription.openai.codex.self.provider_unit": null, "known_overhead_wall_time_ms": 120938.57929063961}
Measurement coverage: {"local.cpu_ms": "0/1", "local.gpu_ms": "0/1", "local.memory_mb_seconds": "0/1", "local.network_bytes": "0/1", "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.cached_input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.output_tokens": "0/1", "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": "0/1", "subscription.openai.codex.self.provider_unit": "0/1"}
Assessment resource break-even uses: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Null means unavailable. Resource break-even is not billed-cash savings or a plugin-price forecast.

Cohort 1: codex "aeep-agent-router/0.154.0 (Debian 13.0.0; aarch64) unknown (aeep-agent-router; 0.8)" / gpt-6-astra / medium
Evidence: live; plan: 2a4cd11aaeb99f49f1107a6e8646f89e4d5b79b1a4854597b6b481c851f707e9

Task family: text.v2:repeated:shape-0
Observed pairs: 0; rejected tasks: 1
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 0 passed, 0 failed, 0 skipped, 1 unknown.
  Candidate use: 0 observed, 0 observed absent, 1 unknown.
  tokens: 0/1 measured; total unknown; observed median unknown.
  agent_wall_seconds: 1/1 measured; total 5.143953708931804; observed median 5.143953708931804.
  verification_wall_seconds: 0/1 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/1 measured; total unknown; observed median unknown.
Unpaired task 62dd13ad61152402608117117a4d02fe699bb8f641076fe0dc8116004e19a829: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Inspection references
[{"arm": "treatment", "receipt_refs": ["a37bbf462a04ff0778086c0e59a359aeabcadbf6e78dd29b654c812f1b3acf95"], "task_sha256": "62dd13ad61152402608117117a4d02fe699bb8f641076fe0dc8116004e19a829", "verification_ref": null}]

Limits
Artifact contents and file changes are not included in these normalized records. Resolve receipt and verification references in the originating run; grades alone do not describe edits.
Access ceilings, spending permission, pending approvals and activation state are not established by this summary. Consult the exact reviewed plan and installation record before further execution.
Describes supplied records; this command does not authenticate referenced receipts, worker conformance or grading evidence.
Only observed tasks are checked. Entire missing pairs cannot be detected without the reviewed plan's expected cases.
Different cohort bindings are never pooled. Repetitions lack a pairing index and are rejected rather than counted as independent cases.
Partial measurements are labeled as known subsets. Resource differences do not override task failures or establish benefit.
Synthetic and replay records cannot establish real model value. Invocation is not evidence of causation.
Confidence and value verdicts require the existing reviewed analysis. Supplied receipt accounting is descriptive; recurring fees are explicit scenarios, not incurred charges or a demonstrated benefit.
Canonical campaign: 1 trials; 1 normalized primary trials; 0 normalization gaps; 0 auxiliary trials.
Canonical analysis includes its frozen conditions, repetitions and auxiliary arms. Descriptive tables below cover only normalized primary trials; they cannot replace the complete campaign or cost ledger.
The canonical verdict is the assessment service's recorded conclusion, not a new toolkit qualification, independent attestation or release approval.
````
