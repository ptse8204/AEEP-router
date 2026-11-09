````text
AEEP evidence summary

Value verdict: NOT_ASSESSED

Descriptive records only. Unknown is not zero; fewer resources do not establish benefit.

Candidate source: "https://github.com/ptse8204/AEEP-router"
Revision: f8f9fba391f32942ebc2471b702c95df936313e7; payload SHA-256: 6b33e3c324a91e011d9da16e4441d8f3f521daec958b8eeaf6ffa9cfb40c89bd
Source metadata is supplied provenance, not verified developer ownership.

Canonical managed assessment
Recorded outcome: insufficient_evidence; qualification passed: False.
Analysis: 238a994bff3f67174e1507e4d4fcf82021f4fe665a3363716f79ec102f00fdf6; campaign: 877da86c28187878d7bad84d8d7b2b199358b22d340fe3ca4130ea70c60f8f7c; operation ledger: e0a3f4d7cbebd6fd8015bcceddc05212960a5d14681c1243c95b3058a0b1c385.
Distinct holdouts: 0; distinct paired cases: 0.
Correctness failures: 0; execution failures: 0.
Expected trial positions: 1; missing: 0; unexpected: 0; duplicate: 0.
Unresolved operations: 0.
Trial wall time includes routing and preflight; separately measured grading is excluded by BenchmarkRunner.
Positive paired resource differences mean control used more. Success gains use treatment minus control. Intervals and guardrails retain the frozen analysis policy.
Journal capture verification (not independent provider metering): {"candidate_loading_unknown": 0, "instructions_loaded": 1, "notice": "Capture verification checks retained journal-to-receipt consistency. Token quantities remain provider-reported; independent provider usage is unverified. Positive skill injection proves instructions loaded, not semantic use. Missing metrics never prove non-use.", "partial": 0, "runs": 1, "unknown": 0, "verified": 1}
Paired measurement coverage: {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": 0, "model.openai.gpt-6.1-sol.subscription.cached_input_tokens": 0, "model.openai.gpt-6.1-sol.subscription.input_tokens": 0, "model.openai.gpt-6.1-sol.subscription.output_tokens": 0, "model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}
Paired resource differences: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.input_tokens": null, "model.openai.gpt-6.1-sol.subscription.output_tokens": null, "model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Uncertainty intervals: {}
Separate worker conditions: {"fresh-worker": {"break_even_uses": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.input_tokens": null, "model.openai.gpt-6.1-sol.subscription.output_tokens": null, "model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "paired_measurement_cases": {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": 0, "model.openai.gpt-6.1-sol.subscription.cached_input_tokens": 0, "model.openai.gpt-6.1-sol.subscription.input_tokens": 0, "model.openai.gpt-6.1-sol.subscription.output_tokens": 0, "model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}, "paired_savings": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.input_tokens": null, "model.openai.gpt-6.1-sol.subscription.output_tokens": null, "model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "savings_interval": {}}}
Utility, guardrails and challengers: {"analysis": "all_assigned_cases", "benefit": false, "candidate_selection_filter": false, "challengers": {}, "complete": false, "dominated": false, "family_error_rate": 0.05, "guardrails_passed": false, "metrics": {"wall_time_ms": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}}, "stage": "qualification"}
Workflow overhead accounting: {"assessment_plan_ids": ["plan_c695ca2ce2df4928b6a2f8671d887878"], "completion": "resolve the terminal operation_measurement after this command returns", "definition_ref": "7952507269ae6a3fca07f334da26b5790eae808aa0091544fbbe09d3dc0aa0fc", "ledger": "existing assessment operation_start / operation_measurement", "measurement_scope": "exclusive wrapper wall time and process CPU; canonical execution intervals excluded", "operation_id": "workflow:skillsbench-react-execution-react-sol-permitted-path-20261109:execute", "token_memory_cash_measurements": "UNKNOWN; no zero values inferred"}
Assessment usage, including known subtotals: {"assessment_total.local.cpu_ms": null, "assessment_total.local.gpu_ms": null, "assessment_total.local.memory_mb_seconds": null, "assessment_total.local.network_bytes": null, "assessment_total.model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "assessment_total.model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "assessment_total.model.openai.gpt-6.1-sol.subscription.input_tokens": null, "assessment_total.model.openai.gpt-6.1-sol.subscription.output_tokens": null, "assessment_total.model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "assessment_total.subscription.openai.codex.self.provider_unit": null, "assessment_wall_time_ms": 285017.1368320662, "campaign_total.local.cpu_ms": null, "campaign_total.local.gpu_ms": null, "campaign_total.local.memory_mb_seconds": null, "campaign_total.local.network_bytes": null, "campaign_total.model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "campaign_total.model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "campaign_total.model.openai.gpt-6.1-sol.subscription.input_tokens": null, "campaign_total.model.openai.gpt-6.1-sol.subscription.output_tokens": null, "campaign_total.model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "campaign_total.subscription.openai.codex.self.provider_unit": null, "campaign_wall_time_ms": 122865.29741698178, "included_invocation_guard_ms": 128.03633301518857, "included_routing_overhead_ms": 9.931500011589378, "known_campaign_subtotal.local.cpu_ms": null, "known_campaign_subtotal.local.gpu_ms": null, "known_campaign_subtotal.local.memory_mb_seconds": null, "known_campaign_subtotal.local.network_bytes": null, "known_campaign_subtotal.model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6.1-sol.subscription.input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6.1-sol.subscription.output_tokens": null, "known_campaign_subtotal.model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "known_campaign_subtotal.subscription.openai.codex.self.provider_unit": null, "known_campaign_wall_time_ms": 122865.29741698178, "known_overhead_subtotal.local.cpu_ms": 48838.384999999995, "known_overhead_subtotal.local.gpu_ms": null, "known_overhead_subtotal.local.memory_mb_seconds": null, "known_overhead_subtotal.local.network_bytes": null, "known_overhead_subtotal.model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6.1-sol.subscription.input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6.1-sol.subscription.output_tokens": null, "known_overhead_subtotal.model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "known_overhead_subtotal.subscription.openai.codex.self.provider_unit": null, "known_overhead_wall_time_ms": 162151.8394150844}
Measurement coverage: {"local.cpu_ms": "0/1", "local.gpu_ms": "0/1", "local.memory_mb_seconds": "0/1", "local.network_bytes": "0/1", "model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": "0/1", "model.openai.gpt-6.1-sol.subscription.cached_input_tokens": "0/1", "model.openai.gpt-6.1-sol.subscription.input_tokens": "0/1", "model.openai.gpt-6.1-sol.subscription.output_tokens": "0/1", "model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": "0/1", "subscription.openai.codex.self.provider_unit": "0/1"}
Assessment resource break-even uses: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6.1-sol.subscription.cache_write_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.cached_input_tokens": null, "model.openai.gpt-6.1-sol.subscription.input_tokens": null, "model.openai.gpt-6.1-sol.subscription.output_tokens": null, "model.openai.gpt-6.1-sol.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Null means unavailable. Resource break-even is not billed-cash savings or a plugin-price forecast.

Cohort 1: codex "aeep-agent-router/0.159.1 (Debian 13.0.0; aarch64) unknown (aeep-agent-router; 0.8)" / gpt-6.1-sol / medium
Evidence: live; plan: 3c66d9cf81f33da89a155fdf06bad835c8fa3f8b3c12b35a2f6a2acee6db9776

Task family: skillsbench:react-performance-debugging
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
  tokens: 1/1 measured; total 193048; observed median 193048.
  agent_wall_seconds: 1/1 measured; total 122.86529741698178; observed median 122.86529741698178.
  verification_wall_seconds: 1/1 measured; total 36.71775754104601; observed median 36.71775754104601.
  setup_wall_seconds: 0/1 measured; total unknown; observed median unknown.
Unpaired task 6a5db3d614f0e71390becbd9dceee2c15628a06086ddbaa332eaa3a86ed73cd7: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
All task observations, including failed, forced and unpaired runs: [{"agent_wall_seconds": 122.86529741698178, "arm": "treatment", "binary_task_score": 1, "execution_status": "completed", "raw_tokens": {"cached_input_tokens": 146560, "cached_semantics": "included_in_input", "input_tokens": 188327, "output_tokens": 4721, "reasoning_output_tokens": 508, "reasoning_semantics": "included_in_output", "source_ref": "92347965ca611b6334375078e8094aaf90cba682ffd3f998b6d8e05fb35050b6"}, "receipt_refs": ["92347965ca611b6334375078e8094aaf90cba682ffd3f998b6d8e05fb35050b6"], "retries": 0, "run_id": "trial_plan_c695ca2ce2df4928b6a2f8671d887878_react-performance-debugging_skillsbench-react-sol-permitted.treatment_fresh-worker_0", "task_sha256": "6a5db3d614f0e71390becbd9dceee2c15628a06086ddbaa332eaa3a86ed73cd7", "tokens": 193048, "verification": "pass", "verification_ref": "cd3d5e0107d3d125eab3c511409f556679fb809e7470323340bb5ab616f39974", "verification_wall_seconds": 36.71775754104601}]
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Inspection references
[{"arm": "treatment", "receipt_refs": ["92347965ca611b6334375078e8094aaf90cba682ffd3f998b6d8e05fb35050b6"], "task_sha256": "6a5db3d614f0e71390becbd9dceee2c15628a06086ddbaa332eaa3a86ed73cd7", "verification_ref": "cd3d5e0107d3d125eab3c511409f556679fb809e7470323340bb5ab616f39974"}]

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
