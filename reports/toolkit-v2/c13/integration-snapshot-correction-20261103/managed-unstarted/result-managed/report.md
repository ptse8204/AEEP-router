````text
AEEP evidence summary

Value verdict: NOT_ASSESSED

Descriptive records only. Unknown is not zero; fewer resources do not establish benefit.

Candidate source: "https://github.com/ptse8204/AEEP-router"
Revision: f8f9fba391f32942ebc2471b702c95df936313e7; payload SHA-256: 6b33e3c324a91e011d9da16e4441d8f3f521daec958b8eeaf6ffa9cfb40c89bd
Source metadata is supplied provenance, not verified developer ownership.

Canonical managed assessment
Recorded outcome: insufficient_evidence; qualification passed: False.
Analysis: faa17bf2824059668ff11bc97786047fe81078de69ca05dc268573a33af2cc4c; campaign: 72f6a46cc3941578537f834a729806d4e19726a054b74b6f85048985029a698b; operation ledger: 1b9973d3abb9056bd564509b6d0e94fb39762e4f9d77a089762a8d025ca4f090.
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
Assessment usage, including known subtotals: {"assessment_total.local.cpu_ms": null, "assessment_total.local.gpu_ms": null, "assessment_total.local.memory_mb_seconds": null, "assessment_total.local.network_bytes": null, "assessment_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "assessment_total.subscription.openai.codex.self.provider_unit": null, "assessment_wall_time_ms": 120505.23633277044, "campaign_total.local.cpu_ms": null, "campaign_total.local.gpu_ms": null, "campaign_total.local.memory_mb_seconds": null, "campaign_total.local.network_bytes": null, "campaign_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "campaign_total.subscription.openai.codex.self.provider_unit": null, "campaign_wall_time_ms": 63996.416167356074, "included_invocation_guard_ms": 122.26091604679823, "included_routing_overhead_ms": 11.335625313222408, "known_campaign_subtotal.local.cpu_ms": null, "known_campaign_subtotal.local.gpu_ms": null, "known_campaign_subtotal.local.memory_mb_seconds": null, "known_campaign_subtotal.local.network_bytes": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_campaign_subtotal.subscription.openai.codex.self.provider_unit": null, "known_campaign_wall_time_ms": 63996.416167356074, "known_overhead_subtotal.local.cpu_ms": 11073.755000000001, "known_overhead_subtotal.local.gpu_ms": null, "known_overhead_subtotal.local.memory_mb_seconds": null, "known_overhead_subtotal.local.network_bytes": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_overhead_subtotal.subscription.openai.codex.self.provider_unit": null, "known_overhead_wall_time_ms": 56508.82016541436}
Measurement coverage: {"local.cpu_ms": "0/1", "local.gpu_ms": "0/1", "local.memory_mb_seconds": "0/1", "local.network_bytes": "0/1", "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.cached_input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.input_tokens": "0/1", "model.openai.gpt-6-astra.subscription.output_tokens": "0/1", "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": "0/1", "subscription.openai.codex.self.provider_unit": "0/1"}
Assessment resource break-even uses: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Null means unavailable. Resource break-even is not billed-cash savings or a plugin-price forecast.

Cohort 1: codex "aeep-agent-router/0.154.0 (Debian 13.0.0; aarch64) unknown (aeep-agent-router; 0.8)" / gpt-6-astra / medium
Evidence: live; plan: ac40582f1c0f40914dcb35c74f2a837f4f8e098ebcdf1965f415ffbbe7f803e0

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
  tokens: 1/1 measured; total 192179; observed median 192179.
  agent_wall_seconds: 1/1 measured; total 63.996416167356074; observed median 63.996416167356074.
  verification_wall_seconds: 1/1 measured; total 2.037404874805361; observed median 2.037404874805361.
  setup_wall_seconds: 0/1 measured; total unknown; observed median unknown.
Unpaired task 8bdf4c5cd84081817889637e9b43f8017654a4eaa7523f6fb12c9a93ee6132c1: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
All task observations, including failed, forced and unpaired runs: [{"agent_wall_seconds": 63.996416167356074, "arm": "treatment", "binary_task_score": 1, "execution_status": "completed", "raw_tokens": {"cached_input_tokens": 145920, "cached_semantics": "included_in_input", "input_tokens": 190532, "output_tokens": 1647, "reasoning_output_tokens": 39, "reasoning_semantics": "included_in_output", "source_ref": "b6a65eb96c095048ef8d53358ea301e50760f529d0b15f6310c431a1c619de50"}, "receipt_refs": ["b6a65eb96c095048ef8d53358ea301e50760f529d0b15f6310c431a1c619de50"], "retries": 0, "run_id": "trial_plan_845bb483f77b4d44a7700c70d0cf282f_matthewwithanm__python-markdownify-200_toolkit-ase-stack-20261103.treatment_fresh-worker_0", "task_sha256": "8bdf4c5cd84081817889637e9b43f8017654a4eaa7523f6fb12c9a93ee6132c1", "tokens": 192179, "verification": "pass", "verification_ref": "3c5bd7575b2dfabdd247b50196afda273f557bae811d48908eb0be20b994165b", "verification_wall_seconds": 2.037404874805361}]
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Inspection references
[{"arm": "treatment", "receipt_refs": ["b6a65eb96c095048ef8d53358ea301e50760f529d0b15f6310c431a1c619de50"], "task_sha256": "8bdf4c5cd84081817889637e9b43f8017654a4eaa7523f6fb12c9a93ee6132c1", "verification_ref": "3c5bd7575b2dfabdd247b50196afda273f557bae811d48908eb0be20b994165b"}]

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
Canonical campaign: 1 trials; 1 normalized primary trials; 0 normalization gaps; 0 auxiliary trials.
Canonical analysis includes its frozen conditions, repetitions and auxiliary arms. Descriptive tables below cover only normalized primary trials; they cannot replace the complete campaign or cost ledger.
The canonical verdict is the assessment service's recorded conclusion, not a new toolkit qualification, independent attestation or release approval.
````
