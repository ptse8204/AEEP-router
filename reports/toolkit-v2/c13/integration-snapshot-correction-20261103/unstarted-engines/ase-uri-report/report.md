````text
AEEP evidence summary

Value verdict: NOT_ASSESSED

Descriptive records only. Unknown is not zero; fewer resources do not establish benefit.

Candidate source: "https://github.com/ptse8204/AEEP-router"
Revision: f8f9fba391f32942ebc2471b702c95df936313e7; payload SHA-256: 6b33e3c324a91e011d9da16e4441d8f3f521daec958b8eeaf6ffa9cfb40c89bd
Source metadata is supplied provenance, not verified developer ownership.

Canonical managed assessment
Recorded outcome: insufficient_evidence; qualification passed: False.
Analysis: fb043b1225f5ffb87662e996e7c69b4ba77225fa33154207418250136e46d751; campaign: 0d2ccfd99b519c46d8d2dd143b07672f8bd2dc4ed80a0d161413999f8d91f925; operation ledger: 2b92478ae75a3b321535caa605497fc1084c58e6ab40bd38a7f7ee21fa31929d.
Distinct holdouts: 0; distinct paired cases: 0.
Correctness failures: 0; execution failures: 0.
Expected trial positions: 1; missing: 0; unexpected: 0; duplicate: 0.
Unresolved operations: 0.
Trial wall time includes routing and preflight; separately measured grading is excluded by BenchmarkRunner.
Positive paired resource differences mean control used more. Success gains use treatment minus control. Intervals and guardrails retain the frozen analysis policy.
Journal capture verification (not independent provider metering): {"candidate_loading_unknown": 0, "instructions_loaded": 1, "notice": "Capture verification checks retained journal-to-receipt consistency. Token quantities remain provider-reported; independent provider usage is unverified. Positive skill injection proves instructions loaded, not semantic use. Missing metrics never prove non-use.", "partial": 0, "runs": 1, "unknown": 0, "verified": 1}
Paired measurement coverage: {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": 0, "model.openai.gpt-6-astra.subscription.cached_input_tokens": 0, "model.openai.gpt-6-astra.subscription.input_tokens": 0, "model.openai.gpt-6-astra.subscription.output_tokens": 0, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}
Paired resource differences: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Uncertainty intervals: {}
Separate worker conditions: {"fresh-worker": {"break_even_uses": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "paired_measurement_cases": {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": 0, "model.openai.gpt-6-astra.subscription.cached_input_tokens": 0, "model.openai.gpt-6-astra.subscription.input_tokens": 0, "model.openai.gpt-6-astra.subscription.output_tokens": 0, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}, "paired_savings": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "savings_interval": {}}}
Utility, guardrails and challengers: {"analysis": "all_assigned_cases", "benefit": false, "candidate_selection_filter": false, "challengers": {}, "complete": false, "dominated": false, "family_error_rate": 0.05, "guardrails_passed": false, "metrics": {"wall_time_ms": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}}, "stage": "qualification"}
Workflow overhead accounting: {"coverage": "NOT_RECORDED", "notice": "No workflow overhead scope was selected; execution ledger alone is incomplete composed cost coverage."}
Assessment usage, including known subtotals: {"assessment_total.local.cpu_ms": null, "assessment_total.local.gpu_ms": null, "assessment_total.local.memory_mb_seconds": null, "assessment_total.local.network_bytes": null, "assessment_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "assessment_total.subscription.openai.codex.self.provider_unit": null, "assessment_wall_time_ms": 108663.8676263392, "campaign_total.local.cpu_ms": null, "campaign_total.local.gpu_ms": null, "campaign_total.local.memory_mb_seconds": null, "campaign_total.local.network_bytes": null, "campaign_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "campaign_total.subscription.openai.codex.self.provider_unit": null, "campaign_wall_time_ms": 49341.09479095787, "included_invocation_guard_ms": 128.33595741540194, "included_routing_overhead_ms": 4.397000186145306, "known_campaign_subtotal.local.cpu_ms": null, "known_campaign_subtotal.local.gpu_ms": null, "known_campaign_subtotal.local.memory_mb_seconds": null, "known_campaign_subtotal.local.network_bytes": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_campaign_subtotal.subscription.openai.codex.self.provider_unit": null, "known_campaign_wall_time_ms": 49341.09479095787, "known_overhead_subtotal.local.cpu_ms": 12055.832223999998, "known_overhead_subtotal.local.gpu_ms": null, "known_overhead_subtotal.local.memory_mb_seconds": 3314.0037600942233, "known_overhead_subtotal.local.network_bytes": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_overhead_subtotal.subscription.openai.codex.self.provider_unit": null, "known_overhead_wall_time_ms": 59322.77283538133}
Measurement coverage: {"local.cpu_ms": "0/1", "local.gpu_ms": "0/1", "local.memory_mb_seconds": "0/1", "local.network_bytes": "0/1", "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.cached_input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.output_tokens": "0/1", "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": "0/1", "subscription.openai.codex.self.provider_unit": "0/1"}
Assessment resource break-even uses: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Null means unavailable. Resource break-even is not billed-cash savings or a plugin-price forecast.

Cohort 1: codex "aeep-agent-router/0.154.0 (Debian 13.0.0; aarch64) unknown (aeep-agent-router; 0.8)" / gpt-6-astra / medium
Evidence: live; plan: a7063c2933cbc35ac03a762cd24c6b323d0036c5a3c325ea46d6f02c90a42b77

Task family: source-family:ff6bbbb351dc943479c91b2ac8eb920238bb018bc543a86ac76712d58f006a14
Observed pairs: 0; rejected tasks: 1
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 1 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 1 unknown.
  tokens: 1/1 measured; total 130353; observed median 130353.
  agent_wall_seconds: 1/1 measured; total 49.34109479095787; observed median 49.34109479095787.
  verification_wall_seconds: 1/1 measured; total 2.0914121670648456; observed median 2.0914121670648456.
  setup_wall_seconds: 0/1 measured; total unknown; observed median unknown.
Unpaired task e003465927fc639a463748a7c21b55d3508cd7c86ba9314abd8ee0c967204d4d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
All task observations, including failed, forced and unpaired runs: [{"agent_wall_seconds": 49.34109479095787, "arm": "treatment", "binary_task_score": 1, "execution_status": "completed", "raw_tokens": {"cached_input_tokens": 111232, "cached_semantics": "included_in_input", "input_tokens": 128909, "output_tokens": 1444, "reasoning_output_tokens": 68, "reasoning_semantics": "included_in_output", "source_ref": "c23c117c28d9ee2a197e318bdd1da3d5f51a3a96fcecefb1a778dba3c90bb231"}, "receipt_refs": ["c23c117c28d9ee2a197e318bdd1da3d5f51a3a96fcecefb1a778dba3c90bb231"], "retries": 0, "run_id": "trial_plan_f966c3a56138439aa2aedd84cfe511cd_matthewwithanm__python-markdownify-200_toolkit-ase-stack-20261103.treatment_fresh-worker_0", "task_sha256": "e003465927fc639a463748a7c21b55d3508cd7c86ba9314abd8ee0c967204d4d", "tokens": 130353, "verification": "pass", "verification_ref": "215f843e0c01cea9d477f8d1428c3907298fbbc6cb1f0957f1fd345c2d29e66f", "verification_wall_seconds": 2.0914121670648456}]
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Inspection references
[{"arm": "treatment", "receipt_refs": ["c23c117c28d9ee2a197e318bdd1da3d5f51a3a96fcecefb1a778dba3c90bb231"], "task_sha256": "e003465927fc639a463748a7c21b55d3508cd7c86ba9314abd8ee0c967204d4d", "verification_ref": "215f843e0c01cea9d477f8d1428c3907298fbbc6cb1f0957f1fd345c2d29e66f"}]

Limits
Artifact contents and file changes are not included in these normalized records. Resolve receipt and verification references in the originating run; grades alone do not describe edits.
Access ceilings, spending permission, pending approvals and activation state are not established by this summary. Consult the exact reviewed plan and installation record before further execution.
Describes supplied records; this command does not authenticate referenced receipts, worker conformance or grading evidence.
Only observed tasks are checked. Entire missing pairs cannot be detected without the reviewed plan's expected cases.
Different cohort bindings are never pooled. Repetitions lack a pairing index and are rejected rather than counted as independent cases.
Partial measurements are labeled as known subsets. Resource differences do not override task failures or establish benefit.
Per-task binary scores restate recorded independent pass/fail; they introduce no partial-credit quality rubric. Unknown/skipped grades have no numeric score.
Synthetic and replay records cannot establish real model value. Invocation is not evidence of causation.
Confidence and value verdicts require the existing reviewed analysis. Supplied receipt accounting is descriptive; recurring fees are explicit scenarios, not incurred charges or a demonstrated benefit.
Upstream scheduler timing/token defaults are compatibility artifacts. Only canonical AEEP receipts supply measured usage; the upstream JSON assertion checks the existing protected grade certificate.
Canonical campaign: 1 trials; 1 normalized primary trials; 0 normalization gaps; 0 auxiliary trials.
Canonical analysis includes its frozen conditions, repetitions and auxiliary arms. Descriptive tables below cover only normalized primary trials; they cannot replace the complete campaign or cost ledger.
The canonical verdict is the assessment service's recorded conclusion, not a new toolkit qualification, independent attestation or release approval.
Read-only URI-family serialization adaptation; original label is retained in source-family-map.json. The earlier failed export remains unchanged. This is the same single canonical trial, never an additional observation.
````
