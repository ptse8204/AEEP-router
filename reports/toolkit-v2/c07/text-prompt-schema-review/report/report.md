````text
AEEP evidence summary

Value verdict: NOT_ASSESSED

Descriptive records only. Unknown is not zero; fewer resources do not establish benefit.

Candidate source: "https://github.com/DietrichGebert/ponytail"
Revision: 1d95ff7d39de12d87014ea40d4e22201bddc501b; payload SHA-256: 28db736a30751c76ae4f8649e5f810ae086213f7e15ad601e692b6f87188117e
Source metadata is supplied provenance, not verified developer ownership.

Canonical managed assessment
Recorded outcome: insufficient_evidence; qualification passed: True.
Analysis: 4d7a171eb0891ff5de47504ae6f3bd1828261d6b157c9451ae7b1029408e7484; campaign: e6c87d17e518039aed242331693532f21e07b208db514e50e13b458fabd4aa55; operation ledger: 477c2e11de350c0cec550a8a723380a6878c1a4c976f900ac2e774453431f2d4.
Distinct holdouts: 105; distinct paired cases: 0.
Correctness failures: 0; execution failures: 0.
Expected trial positions: 141; missing: 0; unexpected: 0; duplicate: 0.
Unresolved operations: 0.
Trial wall time includes routing and preflight; separately measured grading is excluded by BenchmarkRunner.
Positive paired resource differences mean control used more. Success gains use treatment minus control. Intervals and guardrails retain the frozen analysis policy.
Paired measurement coverage: {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": 0, "model.openai.gpt-6-astra.subscription.cached_input_tokens": 0, "model.openai.gpt-6-astra.subscription.input_tokens": 0, "model.openai.gpt-6-astra.subscription.output_tokens": 0, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}
Paired resource differences: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Uncertainty intervals: {}
Separate worker conditions: {"fresh-worker": {"break_even_uses": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "paired_measurement_cases": {"local.cpu_ms": 0, "local.gpu_ms": 0, "local.memory_mb_seconds": 0, "local.network_bytes": 0, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": 0, "model.openai.gpt-6-astra.subscription.cached_input_tokens": 0, "model.openai.gpt-6-astra.subscription.input_tokens": 0, "model.openai.gpt-6-astra.subscription.output_tokens": 0, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": 0, "subscription.openai.codex.self.provider_unit": 0, "wall_time_ms": 0}, "paired_savings": {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}, "savings_interval": {}}}
Utility, guardrails and challengers: {"analysis": "all_assigned_cases", "benefit": false, "candidate_selection_filter": false, "challengers": {}, "complete": false, "dominated": false, "family_error_rate": 0.05, "guardrails_passed": false, "metrics": {"input_tokens": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}, "output_tokens": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}, "task_success": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}, "wall_time_ms": {"distinct_pairs": 0, "interval": [], "relative_saving": null, "success_gain": null, "zero_baseline_regression": false}}, "stage": "qualification"}
Assessment usage, including known subtotals: {"assessment_total.local.cpu_ms": null, "assessment_total.local.gpu_ms": null, "assessment_total.local.memory_mb_seconds": null, "assessment_total.local.network_bytes": null, "assessment_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "assessment_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "assessment_total.subscription.openai.codex.self.provider_unit": null, "assessment_wall_time_ms": 1407561.1235906836, "campaign_total.local.cpu_ms": null, "campaign_total.local.gpu_ms": null, "campaign_total.local.memory_mb_seconds": null, "campaign_total.local.network_bytes": null, "campaign_total.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.input_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.output_tokens": null, "campaign_total.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "campaign_total.subscription.openai.codex.self.provider_unit": null, "campaign_wall_time_ms": 1231455.8695058804, "included_invocation_guard_ms": 15111.301624914631, "included_routing_overhead_ms": 693.8006663694978, "known_campaign_subtotal.local.cpu_ms": null, "known_campaign_subtotal.local.gpu_ms": null, "known_campaign_subtotal.local.memory_mb_seconds": null, "known_campaign_subtotal.local.network_bytes": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_campaign_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_campaign_subtotal.subscription.openai.codex.self.provider_unit": null, "known_campaign_wall_time_ms": 1231455.8695058804, "known_overhead_subtotal.local.cpu_ms": 28191.944999999974, "known_overhead_subtotal.local.gpu_ms": null, "known_overhead_subtotal.local.memory_mb_seconds": null, "known_overhead_subtotal.local.network_bytes": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.input_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.output_tokens": null, "known_overhead_subtotal.model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "known_overhead_subtotal.subscription.openai.codex.self.provider_unit": null, "known_overhead_wall_time_ms": 176105.25408480316}
Measurement coverage: {"local.cpu_ms": "0/141", "local.gpu_ms": "0/141", "local.memory_mb_seconds": "0/141", "local.network_bytes": "0/141", "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": "0/141", "model.openai.gpt-6-astra.subscription.cached_input_tokens": "0/141", "model.openai.gpt-6-astra.subscription.input_tokens": "0/141", "model.openai.gpt-6-astra.subscription.output_tokens": "0/141", "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": "0/141", "subscription.openai.codex.self.provider_unit": "0/141"}
Assessment resource break-even uses: {"local.cpu_ms": null, "local.gpu_ms": null, "local.memory_mb_seconds": null, "local.network_bytes": null, "model.openai.gpt-6-astra.subscription.cache_write_input_tokens": null, "model.openai.gpt-6-astra.subscription.cached_input_tokens": null, "model.openai.gpt-6-astra.subscription.input_tokens": null, "model.openai.gpt-6-astra.subscription.output_tokens": null, "model.openai.gpt-6-astra.subscription.reasoning_output_tokens": null, "subscription.openai.codex.self.provider_unit": null, "wall_time_ms": null}
Null means unavailable. Resource break-even is not billed-cash savings or a plugin-price forecast.

Cohort 1: codex "aeep-agent-router/0.154.0 (Debian 13.0.0; aarch64) unknown (aeep-agent-router; 0.8)" / gpt-6-astra / medium
Evidence: live; plan: 5f9608ceeda460d37c8061e80cf4e7c69ae78e37c80d082ca379e1a720d60225

Task family: text.v2:distractor:shape-0
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59366; observed median 9894.0.
  agent_wall_seconds: 6/6 measured; total 54.884730958845466; observed median 9.22616870852653.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 0f77621249c5ffb373aafd67ed106df81600e8cab9fdec032334d46621749e0f: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 38816e1a0552e4169aa1e3127bae7e9ebf8b0f8ea99e868486fd630b409dc4cc: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 4e7e04ca016fa407fbd19d3e6724981cdbd5e8fd0afb9d135bc0dded8697db2e: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c4d3a9041c863f6b63b28d006b0e6572c7eee80ab9ff7820821c2592cf180fa7: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task e34661db83ec8a7c879c14ab8427fb9fba0a28456fd94586d2f499a37dedb863: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task eb6959df06775da774c447ac425788fc09fe0860266f06e0e642b1803d7fc36d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:distractor:shape-1
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49525; observed median 9905.
  agent_wall_seconds: 5/5 measured; total 47.20042966492474; observed median 9.170311665860936.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 10064b913a58eba0486b95eadc5eb0cd3afb92d14dc5348458376362e0244ac6: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 52a50884863027d8f62bbd1f422ee4c6ba68ce83784c1451f61a2164269f4e71: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 7044b611e2e6bea0b4c9b50d5e55c10eb8bf09923b0ad06f42b2414916f33f6f: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8300f2720f5054ba9cfa8bc3836e6d6f09287e2e91424f324267b65f0f269e7b: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8ce0ad065dda5ac0ec2953ba18e0da082e9c412f10df7a999d8fda6491644eaa: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:distractor:shape-2
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49400; observed median 9879.
  agent_wall_seconds: 5/5 measured; total 34.66666616778821; observed median 6.9376012498978525.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 0dc7fa848fd78e3bcb3bb0c5877af91aa4455f67dc841d2f00bdabd430dafb49: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 5b7018bbfc315feca338b079bf7c1e911a43f81c256345e2f6ae4a5d06deae44: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task d32cf6de2806a9c573cae0d90512e75cd557d2d09f6ed9ed3fa8becab87f8ca0: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task ee297e7cfa2195db8cfa7f7754232c63861c60f1c09c419f54427105d30b12d9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task f156ae405a44ebcd651b87aa3e0636ee50a9c384f4f1a4d28b7b712445eaf8c5: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:distractor:shape-3
Observed pairs: 0; rejected tasks: 4
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 4 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 4 unknown.
  tokens: 4/4 measured; total 39564; observed median 9891.0.
  agent_wall_seconds: 4/4 measured; total 36.96880737412721; observed median 9.536777353961952.
  verification_wall_seconds: 0/4 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/4 measured; total unknown; observed median unknown.
Unpaired task 4b7936146813d33c5c8c51ef08291f0ff1a80c5b389feef381324ec525ccccbf: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 5cc9aaf82f2d18ebf76dabf042b405dab8dc3d07e94936657caccd48c01f0e68: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 72fbec7a95f1be2477888e8ba2a61336b729064816d34872711c0517901ee7b4: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task b412a361fe09ac6ddb086107ab223e49a5c95c91f28d950998b195ea3ce69b9d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:invalid:shape-0
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59184; observed median 9864.0.
  agent_wall_seconds: 6/6 measured; total 47.26971579203382; observed median 7.82649764593225.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 7031f79d7fb6653411508ac1b06d98458062c423c0836bba6d8b3f4c8978b3c6: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 7bc4edf00e5ac3c3f1d78fdeae5c8ef2c8c93d18195fa23546daf82fdb896aef: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8d733c59cd0e691338a392e098021e257ccfab9aa40272a2dd2dd07b6296f4fa: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task adab8f4227b6cdcc2e65a1f4f3d0a32d589a2893d766d4c66f2220d1467703f6: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task bcdafa3f9252f58f518273930b61146e8bdbc8aac3cb7fd0638e227b84180d97: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task d4a3558f958b78ab059ff441c47fad4d399a4cc8ebec9b08fce50746136d4665: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:invalid:shape-1
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49362; observed median 9873.
  agent_wall_seconds: 5/5 measured; total 45.26032625022344; observed median 8.63610037509352.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 07f6f57e38ca1b707c748fee5ee855d8570613dc3d641e7b1a35acd34f8e31a4: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task ab10745df44b299d3b71851e90466b190b238e7fb3b5d667a811b66f83d25076: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task b8e8c0408db65161457981bb4fc60c5d0fdb3f3a47ef63694729e88f0aeac0ef: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c3a747538082927a145b87e5f7e2179235f614652cd9b0ed741a500c8c988648: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task fdbbf6f4363ab7398c6539de9e4b72a4dc01523821a57ea2d3195ad96ad74679: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:invalid:shape-2
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49299; observed median 9859.
  agent_wall_seconds: 5/5 measured; total 43.94760921038687; observed median 7.343621625099331.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 0b7606845fbc817ba8c117b21e680c674bfc48442f10c35b69dd3a086ed802f1: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 201e1e0fbfa29a9b229963920685aeb22bb0ad439665504b3a7162ff19d9b417: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 7253502d472e3dc845c7e74eef9b07df0c9b4c7f19a6e2bc3b026a6e53c9dae3: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 72e480883fd7939855992c0321c8321ac78ac8168045b7c1d78510f2aaf44f82: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task eea4327f104be13ce4e22f766c4b437a3f726fa9262155c98d9cfc32733a4392: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:invalid:shape-3
Observed pairs: 0; rejected tasks: 4
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 4 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 4 unknown.
  tokens: 4/4 measured; total 39459; observed median 9864.5.
  agent_wall_seconds: 4/4 measured; total 32.906092543154955; observed median 8.146529125515372.
  verification_wall_seconds: 0/4 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/4 measured; total unknown; observed median unknown.
Unpaired task 69fc3c077aa11feaf165eb35ab7b8ec742fa4015bacb4221edd004e0fd7c7da1: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a4affe448dca3812c8bb29872f5d89ae3b49764d1b39797cc68c2a96f98aaae9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c2d3ae55e88f5a594cc8f47bb244020ccbd418f21a2bdaf7930fc4ee245cee26: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task ce23bc3034a2a7734222c5bf98a20b35430a6a53b5ac82eca51ee28d06541b11: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:optional:shape-0
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59257; observed median 9877.0.
  agent_wall_seconds: 6/6 measured; total 49.6631974587217; observed median 7.880134854000062.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 0992670b39958e267675f2c8e56be72d0cd4dd224a6d493617920f7f5f338618: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 0cf4515894a3704f82aa637cc6eda76ca581ce5561dbfe4b89740d85c83ba19f: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 40e17fff94c25a14ec87af9e83aac131be04f30a919b48352603553c79237175: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 68684087a0a849ed47fc2cb1f64134370ffc2d5e63baff159e52c59360818d35: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 80a55dea2d9ece2c3df42c16279378461e8b30a394834c623d8f4f2e479ff7a2: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 9b0f32ef27dc3b03f9b07c9ba92c89fe6b9b778e66d703edb85e8bdc9036d4c9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:optional:shape-1
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49442; observed median 9890.
  agent_wall_seconds: 5/5 measured; total 39.89288633177057; observed median 7.5859547078143805.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 00fb81426a05adcc8a0fb94b6e56e05b96ba2ea19265a26c2b7b5125dddb0be8: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 83b5edffb26c22d27993d8c489732b48c686d7eb8673e86ad89ed3fab0af12b7: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a76eebfa743d8d5f8cf7f0e34bc06b7e350569a96a58a1b9e172fd5a5eb77eeb: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task b4f5e5bacce7796f595315d3b0bda0d8622819c1ff427a522db41cbbdf30bdbd: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c0bd2d0e80a30e28149addd5ab749028c57ba7a24eabff37f58f02e67f5d74cd: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:optional:shape-2
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49331; observed median 9865.
  agent_wall_seconds: 5/5 measured; total 33.21978783304803; observed median 5.908248541876674.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 1ad92687725d7ad2d7dcf46d417481b2ee395ac2d7a3968e01d48ce7a7674089: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 22e3e2afb41600ab8f5beb6b152a7563ba7c59791d1c969ef7e35df5a6ab7ea1: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 7659d47cf0f63c08d36fdf2067f85eadd2b0981d78bde19dd15a8520ec124978: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 88b4da2f66b4b9b0679f215bac0f19533b0b0831fe4ca90aa86842b8988cb2a9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a8d00362ac9132886d77f91b88ba15d38c386fa8f47b493a9aaccf7f0d17cb64: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:optional:shape-3
Observed pairs: 0; rejected tasks: 4
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 4 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 4 unknown.
  tokens: 4/4 measured; total 39512; observed median 9878.5.
  agent_wall_seconds: 4/4 measured; total 57.449990834342316; observed median 11.657736854511313.
  verification_wall_seconds: 0/4 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/4 measured; total unknown; observed median unknown.
Unpaired task 44154786ebd9d583f1a84d1797eb1ce059066f69dec1ba117e5349fa0da676ed: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 6eb021ef27afb2adb0b04b39b8207f273f36d1a1165ff423177081ee19feafa7: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8ed5c589b91a2bff0969125f210e0fafdb74d3593e06e7c0b13da03d67290e7e: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task f93b02d73fcf7047ba969b76b2c4e90ec60c950adbf1bbd67bb89143d14728b1: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:plain:shape-0
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59304; observed median 9883.0.
  agent_wall_seconds: 6/6 measured; total 56.00077095837332; observed median 7.976984666544013.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 4fd9bde1604d3043df2923121e52f15eb215f2d5cc6837f615ba3f208e49227d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 626ca525393dbc1c83f3751f74861205056af4264f770d1134173423a0ca6ad2: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 9223d60b320839ae9cfb58d8820a4d1018862feb4198331565f68c9f969654b7: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a446a304b1bddef91913332f3f56c5abc2ad1c48ffc4845037434b3a311cc041: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task e452d52180c378ed047850760debfc329aa26ae154273ead40084fefeabb53bc: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task fcd499c930b498454c45477a886db23758c8828d9deb22d5450f48f696d3d886: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:plain:shape-1
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59374; observed median 9895.0.
  agent_wall_seconds: 6/6 measured; total 49.8287210422568; observed median 7.782658603973687.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 052d05009158ebe8f45e951ab17e0565c0847c5c224eb1377726ddabbaa52780: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8f09dfac198bae1fb478e62d7a42a50f5db1202a4bcdf46f54c1e9fd149e8f99: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task bc182e2d6dbb4c5386b761cc2e82175600da6d7e20e78deeba326a2c28633dc0: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task bf693e4d425b5a8d9cc6f0d9d3ec4f77fa7b37da3d4e2781dff8d6e9d4db5c05: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c356d85bfb50e6254320f886d82dc1e19ef32636b8b97329c81bd2c43316d792: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task f9a2e93f300d9374cd8e32bc654310db7e988a9b3163de9f234c97e52852768d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:plain:shape-2
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49365; observed median 9874.
  agent_wall_seconds: 5/5 measured; total 45.09504116605967; observed median 9.868206749903038.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 40d02f69668fe0a090b3acd78f823e9ce3f32f2b289b9264fb730e7132d61edf: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 55acdc04d209fdb7e324a62bc8792c7442002ccec8ff582d2bf00ebb31fc1a72: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8f8cbe4f45948fcb04ba3c30a0c915c3923a8093e0eebb965e0b4a4d9e1d711f: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 9edcb8b2cebd5a8a320c0b1ca9823349423b72b04a13ef82c1dbed5f37ed5e64: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task f5c080bcc15bc333d45cf0d12cad2b9f61f6efd45a3de1137131cf53ce0fd92e: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:plain:shape-3
Observed pairs: 0; rejected tasks: 4
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 4 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 4 unknown.
  tokens: 4/4 measured; total 39555; observed median 9888.0.
  agent_wall_seconds: 4/4 measured; total 32.68876516795717; observed median 7.516228458960541.
  verification_wall_seconds: 0/4 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/4 measured; total unknown; observed median unknown.
Unpaired task 073fc5a93593665d7867a068497371340108e8273cf062dd00312c3e9941986c: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 2e95effc2e9c688deed32c338d1d6da797c75b387c30019fa0c4345b7e40930c: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 35830dec0775d3126eb2a453344d2843806a472278419a0ff30776e29388308e: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 42fd828737f4bbdce1cfc1a8070dcaf103a3edf15839aff6670060a8a25531d4: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:reordered:shape-0
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59306; observed median 9885.0.
  agent_wall_seconds: 6/6 measured; total 54.07059374987148; observed median 8.738633646513335.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 27fe5106eba709a1e256e042e5bd3097c5328f8782324990e50a4632b0af10bc: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 3fe72cc6152b850e07f3b32e1f8ece758aa23acdcfd89a76c15f30db1ae613db: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 6288873c1d7e5fe62ae3c7a582377a923d77f86f89036c9007b25e1f0c9e472c: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 839d2bb100cc1318623e08cad366a1b94d8d8a89f0447ff0f62025d5fcc6f6d8: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8e232531882a394eb64effeab608ae1549cc6a1949ad0db76dc6bf74dc9e0e53: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task e30c6d6c8b9fcdd7ef5ed090383db088c56619ae1b25b5613c7f47fe3e9a8625: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:reordered:shape-1
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49480; observed median 9895.
  agent_wall_seconds: 5/5 measured; total 43.38903270964511; observed median 8.169557916931808.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 59412be36ba7f130411b468c7ec3d453479704a3a350bbbed343b9d3c2fb5f2b: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c1a4a4899f8d472c1034df46ac487aeec6c19f6769805c84371caa101d260f22: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c4b6e4cff8326b17a86d575f3fae499253cfbe4659181ba6112a07ec21e28891: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task eadd99add005654726d41fb8885c96faec61dc2ba4da85b4f209d93314e937cb: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task fed77ac22f4e86cf21488aac3867e69f3d5385626b91be5ceb0fff8699d36e4f: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:reordered:shape-2
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49384; observed median 9878.
  agent_wall_seconds: 5/5 measured; total 39.11488258372992; observed median 7.32890966697596.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 42d808f5ce5e56e96f3e58d5379066bef3ee6af0b9fb05831d5a430873b77ff2: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 6324c8ab68d010ba36c7645b753492691fad6535b5e938580bb5f2ca8463fe10: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 6f4858f6f7a717b4e33b2753aa9f1a97d7bbce33586456728a3c16b6c742c2b4: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task e4ac9a79a514bfc9cff04d1be0ebbf104e1526aaecbf8dd5ecca23403b82a8f5: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task eecae7585bda4ab6cc55e9478fbc0231fa344ca66ee504992ceda8e2f33dd5fb: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:reordered:shape-3
Observed pairs: 0; rejected tasks: 4
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 4 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 4 unknown.
  tokens: 4/4 measured; total 39548; observed median 9885.5.
  agent_wall_seconds: 4/4 measured; total 36.23612666758709; observed median 9.70510422938969.
  verification_wall_seconds: 0/4 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/4 measured; total unknown; observed median unknown.
Unpaired task 357b0764fe37b0880033823c32bf0625d30af0e128b039a8eb0ca7aa96c95c85: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 9a0e817c865755089cf58dd0aa0171fe558c40d82cb1e94477aedf22bab89880: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task b7736b292b48bc26155d9928e22fa5036f7d610cca1a9faeef0fedf6a8e51f2e: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task ff24033ab09b78125c54b5903bb9c9f5cf46ffb9661e2fb5d972d4b094e77ec1: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:repeated:shape-0
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59196; observed median 9866.0.
  agent_wall_seconds: 6/6 measured; total 51.05273712496273; observed median 8.486805437481962.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 266bec81064b2b7a77770c5c0c8d102f5535ec578c5ec016299475f122a23c79: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 73a2757afe3b456433675b287c0ea44bbf0e5d82d90ac2c686fff02546489dac: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 7c31ca84a1f2d1013ff3987f3dbc21d4497a6c8f4c1fc360b3e899b0a63cf958: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 9d4f26a7dda3d70de02773c8a0373dd81bdecf43dfeba492ca71219fb5b2f037: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a9255ce68456870305396af18dc101f29a7c4d44ce2667c6be55a4f7312d0cc8: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task b637e2df70c5d87652976528b4880dd5ad7da8f41d069b9fe95790c94ce6b524: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:repeated:shape-1
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49365; observed median 9873.
  agent_wall_seconds: 5/5 measured; total 39.76704508205876; observed median 7.8910369160585105.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 6d8137ab755d126cc65528e8f2603246374cbc4c990c3aa3e80c48bd2cd68686: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 7d63f222e4c55b580b65d407cb2e4d156db801cf2d77a9090a0e2909f1f620da: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 990329a4bca12a35a07f4f8cf52e4a4933f69b1fa59f0272c3b5c5b8e3e547db: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a2fc73953f4e75744697bfa50c35c10a721b846cab4abe36426e830b1c0c882c: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task aec1146254e3a385a514d2478c9ac256e164fa4ed21ebc2fd08c00c8f7b4ebe9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:repeated:shape-2
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49299; observed median 9859.
  agent_wall_seconds: 5/5 measured; total 43.76009795884602; observed median 8.823512207949534.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 27cdd30710ff25b29e4170bebb57390e5fe474b629d46a34eef79a192e05ae47: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 396cb101ada7ca8c3c91ae5c882af6aacf64144ef3698726a115804df1063ed3: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 93ba554e1080836e0482fbc2c2e613dbde717fbcb65c4ec04720bcf8e13516dd: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task ca985fbe7380a108d80b36a8ea35a62b72ee9d2bca6489656f9ea3bf37e81cd9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task fc193185031e09a578732fc3f4bc75bd2fae4a8a90c13c3dacbf685cfd19183e: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:repeated:shape-3
Observed pairs: 0; rejected tasks: 4
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 4 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 4 unknown.
  tokens: 4/4 measured; total 39474; observed median 9869.0.
  agent_wall_seconds: 4/4 measured; total 32.05515624885447; observed median 8.065092416480184.
  verification_wall_seconds: 0/4 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/4 measured; total unknown; observed median unknown.
Unpaired task 333c62c3652de577014ce3685d2d6c369f594cedd6745bcc01cf1510e10ecba9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 37862455624da8cc0107b427d4f8eacc465a4868311203b229e13349d1e4084d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a5c37144f1a4bd086a56f754d444543ce858c5ee6ddfc07b9119084d66f468b8: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task d24f24fd4779bcf425998a47a4f3560b710fef426626e59f910a28760b774e69: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:unicode:shape-0
Observed pairs: 0; rejected tasks: 6
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 6 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 6 unknown.
  tokens: 6/6 measured; total 59326; observed median 9888.0.
  agent_wall_seconds: 6/6 measured; total 58.85787095921114; observed median 9.51974912500009.
  verification_wall_seconds: 0/6 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/6 measured; total unknown; observed median unknown.
Unpaired task 5cfb2acd8a695165cfc954aa62c507c1008b34a98e68066a61133826c6b638e8: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 5d2cc41329f8a74999ee5dc2e8395ac342145410ead10e57092360ea7055681a: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 67fa8aea8ca6546a80f29cfc748073580b50f145ead57f8405d2a00eb6a45334: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 6f70176424880bd418c7a1ff251985991cfe54cf6d5ff80d0dda578b4ab05c7f: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task a2ccff38bce2de5a0762dc11a72909cb0e390fc17b4fb96fef60ec0ec8331b39: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task b6345c18eceadc713ee49b2672f449a88a90949c57c60e5a130e4280958cdd5d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:unicode:shape-1
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49499; observed median 9900.
  agent_wall_seconds: 5/5 measured; total 44.83855862612836; observed median 8.786790374899283.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 18090ebd13e975f83a4006593aa1700f8403170bde2246151595e32a5c154c82: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 443a1bf78fdb9c7275787baa44bc2ac14291a3ab36e01ee76f15802f5a4ab48b: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 4d7ee8764cd5231fc11d04df691dc5359578f31eca8f5d3e95591f398ea7363e: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8da6bfd1ed2eeaac9e3fefc89beeadd78e900d7269271b47c2962afee689398d: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task fe35392a78a17a094a48448951db1f8e8115edf017df265020e31eaae3ced5ec: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:unicode:shape-2
Observed pairs: 0; rejected tasks: 5
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 5 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 5 unknown.
  tokens: 5/5 measured; total 49384; observed median 9875.
  agent_wall_seconds: 5/5 measured; total 44.29530412401073; observed median 9.12258983310312.
  verification_wall_seconds: 0/5 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/5 measured; total unknown; observed median unknown.
Unpaired task 2adab41ef8890039e9026b9213bc60ba8d3fd3b2b28dbebdc52183634ad9a607: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 43f521896fbc286e245cf1f49732e6ac4d65238c2ceb948d5180be7e34a1f7b6: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8ce1f36bad9c922420b7dffc309470d1b97db074cd2fce26d5075ddbebe74a79: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 9fe7304dc376dfbe2925596d5e7c5f4bc2334f3fa69fbcc21948f56371979924: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task c6a11c87f699c4454ff7b80b7de4768170abf34f0cd048babcf863fe07330967: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Task family: text.v2:unicode:shape-3
Observed pairs: 0; rejected tasks: 4
Verified-success difference, treatment minus control: unknown; graded pairs: 0/0.
Observed differences are descriptive; no confidence-supported conclusion follows from them.
Control: 0 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 0 unknown.
  tokens: 0/0 measured; total unknown; observed median unknown.
  agent_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  verification_wall_seconds: 0/0 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/0 measured; total unknown; observed median unknown.
Treatment: 4 passed, 0 failed, 0 skipped, 0 unknown.
  Candidate use: 0 observed, 0 observed absent, 4 unknown.
  tokens: 4/4 measured; total 39564; observed median 9890.5.
  agent_wall_seconds: 4/4 measured; total 37.0749249169603; observed median 9.308734208578244.
  verification_wall_seconds: 0/4 measured; total unknown; observed median unknown.
  setup_wall_seconds: 0/4 measured; total unknown; observed median unknown.
Unpaired task 74cd65fcb1d30abc5ca496d941341b755aa36eb3b5931fd22c9b7d9ef2f5ab2b: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 74d12c18d2fae166c76f6d521ab9080b160159ee45a879a9428e9d9611058bc9: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task 8e0c3182ea1ce7fb8bd7f9fa713af4e327d6add07f0aad03bbfbe10fc63496cf: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Unpaired task d2ed5d414e80cb3835f1149a44d3a2c2e4672456e79101472d36d9ac4349afd6: Exactly one observed run per arm is required; missing or repeated arms cannot be paired. Forced invocation is diagnostic only. Candidate exposure is missing or inconsistent.
Cash currency: USD; evidence kind: live.
Control cash: unknown; cost per verified success: unknown.
Treatment cash: unknown; cost per verified success: unknown.
Recurring-fee scenario: null
Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.

Inspection references
[{"arm": "treatment", "receipt_refs": ["56f616de95b04faa807292511f237181bd413c8ab0acb5165322b52f97e99dfe"], "task_sha256": "73a2757afe3b456433675b287c0ea44bbf0e5d82d90ac2c686fff02546489dac", "verification_ref": "171339dcfb63e16cfc63d28296c6159b4862c80fa6cc2dee28e877d510faabbf"}, {"arm": "treatment", "receipt_refs": ["4e1d169a8a7d70d42799e9f8a2ba26a75e8e86bc6c0c60ff0fd5cb44b59b1e90"], "task_sha256": "0992670b39958e267675f2c8e56be72d0cd4dd224a6d493617920f7f5f338618", "verification_ref": "f62e54dd371df7c4e829f3341125fdfd5bbb40b87c01535ec877c12236cd8bce"}, {"arm": "treatment", "receipt_refs": ["e71a0472e9e08a5f56a375d70579e56c929976877c29f4dd9cee38ed0ef38032"], "task_sha256": "6288873c1d7e5fe62ae3c7a582377a923d77f86f89036c9007b25e1f0c9e472c", "verification_ref": "e4718aaca331884e2589916105cd41c003f425e4338a525b3a268d51386db73a"}, {"arm": "treatment", "receipt_refs": ["62aca67b0ed3807f6f404522433c7468ab757d3b84ba50056b749726a1483dec"], "task_sha256": "b6345c18eceadc713ee49b2672f449a88a90949c57c60e5a130e4280958cdd5d", "verification_ref": "4ee998950f705b8e36ba41bbdc497a1f1546813750e7b16ebf85ad43c929b386"}, {"arm": "treatment", "receipt_refs": ["9cd7f33c515fe83282103f2078b39bf8187f518be5d06bbe9963196bff6e0e86"], "task_sha256": "d4a3558f958b78ab059ff441c47fad4d399a4cc8ebec9b08fce50746136d4665", "verification_ref": "400c18b8ca4ce5f543dbaf4edb901fb6b70ac08f91fe774233f947e41c168077"}, {"arm": "treatment", "receipt_refs": ["3a646a96701729482c01f2e62da265b7715777420b4db153509a9d4a291c0727"], "task_sha256": "9223d60b320839ae9cfb58d8820a4d1018862feb4198331565f68c9f969654b7", "verification_ref": "089b5a6305c727597c33e4f3f601b15eef83ed723a56b791ac9ba1c59bee930e"}, {"arm": "treatment", "receipt_refs": ["e4d79280ce1ade3c3f852aad82823931b5fa6ce69ac2409a118242295963b568"], "task_sha256": "eb6959df06775da774c447ac425788fc09fe0860266f06e0e642b1803d7fc36d", "verification_ref": "27b402b51847783ecc8187186ae3840891e38fc060afad667182dc58ad47a82f"}, {"arm": "treatment", "receipt_refs": ["4edd1a3766ec8c633a9184b7803a50ab1afea866f16f56b9ffbf9ab6e4fc0f3e"], "task_sha256": "bf693e4d425b5a8d9cc6f0d9d3ec4f77fa7b37da3d4e2781dff8d6e9d4db5c05", "verification_ref": "b4ee3e7f6f5eafc6b453d51dde36e84365e27375db03437bf1c414f9d40c5eb5"}, {"arm": "treatment", "receipt_refs": ["293304121d230690a13c78ea1cd6831a6d75c221d1f98483045ab15db4f2c5c7"], "task_sha256": "1ad92687725d7ad2d7dcf46d417481b2ee395ac2d7a3968e01d48ce7a7674089", "verification_ref": "60e416d942e804c44a844e18627c9e52fe0c8537c380fed6964a12bffdbeec92"}, {"arm": "treatment", "receipt_refs": ["aa9828d65e21865db4c5e19194f09a4a458e692eb1e058358fdc2eb6c3ab4d97"], "task_sha256": "0cf4515894a3704f82aa637cc6eda76ca581ce5561dbfe4b89740d85c83ba19f", "verification_ref": "f9b8870959963c2a3a7c1886c77b6f53231b1698a15e94c5992300322614face"}, {"arm": "treatment", "receipt_refs": ["20fcd28531677221a639ef3303b7261bbd020d3ab173d1323f755684f3841129"], "task_sha256": "8300f2720f5054ba9cfa8bc3836e6d6f09287e2e91424f324267b65f0f269e7b", "verification_ref": "dce7267539012ba6f3dea15d034400396da2f3fbe21496a739d602c23b3b0edb"}, {"arm": "treatment", "receipt_refs": ["0106d68e72c941d2b9c9cac3b64af402d6f46ec3086a946b77a169a59913a3d8"], "task_sha256": "44154786ebd9d583f1a84d1797eb1ce059066f69dec1ba117e5349fa0da676ed", "verification_ref": "9c38ddba86ab4faf7ceb0cfa847742262a2e51d24770f147aaa4916c7df8056a"}, {"arm": "treatment", "receipt_refs": ["f2d6fde2ec559665ae098ef942f0948ca261f663d5227bade1c30d01c1a1f81a"], "task_sha256": "ce23bc3034a2a7734222c5bf98a20b35430a6a53b5ac82eca51ee28d06541b11", "verification_ref": "01eb3e43d04acd8a07ef90c55f089087c187f2f025bb797120557c846ee29664"}, {"arm": "treatment", "receipt_refs": ["7db498dc3bcb6aa4abddb24ed2de451c40b809a813b5ae67be5584667586535e"], "task_sha256": "d2ed5d414e80cb3835f1149a44d3a2c2e4672456e79101472d36d9ac4349afd6", "verification_ref": "3c5153d7f36f7e7f3b2a49387aac664f29f0bbc65bb347502262002506a35bc6"}, {"arm": "treatment", "receipt_refs": ["95ca0b4e48089e67a47851793d955235a7362c3e1bda7efb16e4fb6893d49464"], "task_sha256": "5cc9aaf82f2d18ebf76dabf042b405dab8dc3d07e94936657caccd48c01f0e68", "verification_ref": "67b37ef7c2a8ae6df251e35ec4a56e7c5a32df250005f5d5f6f27266419c265b"}, {"arm": "treatment", "receipt_refs": ["17d959c98731b0ebdc4a7fd467d2001d97523ea3f7870a700a54e0a09be3ea2e"], "task_sha256": "073fc5a93593665d7867a068497371340108e8273cf062dd00312c3e9941986c", "verification_ref": "0bedc4b728103e1d4a98f6078d8f1cca64b0614453c76aeeb566d0b7557dae21"}, {"arm": "treatment", "receipt_refs": ["16165a1bfdfb9a58a4fa222727271e1a3558d44cc180146125be1b563324eeb6"], "task_sha256": "f156ae405a44ebcd651b87aa3e0636ee50a9c384f4f1a4d28b7b712445eaf8c5", "verification_ref": "061a5e8ddd02965b21ff85a2c7de3634bf446730901a654edfb591615c4193c9"}, {"arm": "treatment", "receipt_refs": ["77a2493ce0508e648987f03c6a10d0c37c060f83bdf25fcead547a5f0dee63da"], "task_sha256": "9edcb8b2cebd5a8a320c0b1ca9823349423b72b04a13ef82c1dbed5f37ed5e64", "verification_ref": "0c54ad66817a23a1cf4ceef0a8f34614759f46f301642bef1368e4ffd19bf3f6"}, {"arm": "treatment", "receipt_refs": ["229e6b319670c5da2ea4b98c44424a1e8ca2130b272a386107863ca5b9764334"], "task_sha256": "eea4327f104be13ce4e22f766c4b437a3f726fa9262155c98d9cfc32733a4392", "verification_ref": "1961ac2eb26befb7922e58f41843f85cade1143a3620ae7ac003388d2ef695f8"}, {"arm": "treatment", "receipt_refs": ["1357c35301f51f2447812a536833261e218af927628563d4747468a65c1c3c8b"], "task_sha256": "18090ebd13e975f83a4006593aa1700f8403170bde2246151595e32a5c154c82", "verification_ref": "515955c407e42ff6d1465f63606d2cd8333741121caff9c0f107f2c9cd8001c8"}, {"arm": "treatment", "receipt_refs": ["4096929f906e665c4746834ffe54165063911816a70201a59d79e9dc4f2aefa1"], "task_sha256": "052d05009158ebe8f45e951ab17e0565c0847c5c224eb1377726ddabbaa52780", "verification_ref": "c951a196978408605b62b69e552457d2f010393fec0dcea136a8163a2f89a0a4"}, {"arm": "treatment", "receipt_refs": ["bcd65b877f19dae9198866b8c2b87d7a1826c346c54bbe57f47da62f0cc71806"], "task_sha256": "a446a304b1bddef91913332f3f56c5abc2ad1c48ffc4845037434b3a311cc041", "verification_ref": "71a651b5dc5cf33f77767df546e470d5ff8cf8f0df3593cfe1df6cb6abd3a958"}, {"arm": "treatment", "receipt_refs": ["6e637869abf37c4d412610352f3e1a6ca28a4d45142b073161f579fc9d046567"], "task_sha256": "b4f5e5bacce7796f595315d3b0bda0d8622819c1ff427a522db41cbbdf30bdbd", "verification_ref": "39250cd51b2e34b0f4083628f51354c8862651e13f506daaa84a3969144cd9f1"}, {"arm": "treatment", "receipt_refs": ["15daed7b41446e77f6d48c963a8790f2172fc4577e57eac7f1a5056d4f9206bf"], "task_sha256": "990329a4bca12a35a07f4f8cf52e4a4933f69b1fa59f0272c3b5c5b8e3e547db", "verification_ref": "854b427123da6fe2939f3656486ea1cd853d0ab0d7c6e126dafca26315aa9fd1"}, {"arm": "treatment", "receipt_refs": ["f8fa1d9ba792d93b68dc274a20c5d10d27c376309083deb20c0420f532037732"], "task_sha256": "93ba554e1080836e0482fbc2c2e613dbde717fbcb65c4ec04720bcf8e13516dd", "verification_ref": "3e7c304fe8752ddf788b4266b05b55de1f08b80e2fc47c8cdad22060ba2ef77c"}, {"arm": "treatment", "receipt_refs": ["a6932d933f82ec240468dafb822f291f7ee5897cb474185e31b61e87980335dd"], "task_sha256": "9d4f26a7dda3d70de02773c8a0373dd81bdecf43dfeba492ca71219fb5b2f037", "verification_ref": "ce170f7b4ce988097e63099d4521d170430f2b82d03f750a536c34970c8980cb"}, {"arm": "treatment", "receipt_refs": ["60a6d621cb998ef823bfd6332f3f059d000a7692d30ca0679e1674627abc1e37"], "task_sha256": "43f521896fbc286e245cf1f49732e6ac4d65238c2ceb948d5180be7e34a1f7b6", "verification_ref": "3e2388f66dfaab5287a3cfdb4aa10793ae6a467f5e76feac04d76c772ba84495"}, {"arm": "treatment", "receipt_refs": ["6bf620b3fe1406cf9def1cd8694e6b28f49b56ca63f099299427f294d457475b"], "task_sha256": "c3a747538082927a145b87e5f7e2179235f614652cd9b0ed741a500c8c988648", "verification_ref": "9c33935ee977f3a26307d4af78c81e868c58d7b5a42bceb1bcce8e1790b3c7d0"}, {"arm": "treatment", "receipt_refs": ["7b609196306152d38e1a696e53c05fa50b61b79cc309e2009a29d171db243301"], "task_sha256": "a5c37144f1a4bd086a56f754d444543ce858c5ee6ddfc07b9119084d66f468b8", "verification_ref": "dc93c32a3a35af91511fbb178eec5c90954f71e4f173e684b22dba4e35c720fd"}, {"arm": "treatment", "receipt_refs": ["03eb03ad665b628876fd7718460a8554a05f9c4ef82274b3704fda37cc523687"], "task_sha256": "c4d3a9041c863f6b63b28d006b0e6572c7eee80ab9ff7820821c2592cf180fa7", "verification_ref": "a1e9b56525c4cd11f19e707eaa58a10bc6c0daedfca24edfb700b783bf99e5db"}, {"arm": "treatment", "receipt_refs": ["d109e5c279b0023b54036b33ccb6b8612a2e1c6d6e4f6f2eb9c2f58baf9e4310"], "task_sha256": "8d733c59cd0e691338a392e098021e257ccfab9aa40272a2dd2dd07b6296f4fa", "verification_ref": "029770c1f5ea2f72c84738f960ef45382d9592b6f540045ac9ca61cc98104ce9"}, {"arm": "treatment", "receipt_refs": ["ae70aed0a428a57a5c3f7f194a79466f4c7cf15b18926b72583657509697f125"], "task_sha256": "67fa8aea8ca6546a80f29cfc748073580b50f145ead57f8405d2a00eb6a45334", "verification_ref": "3b0c91f28926e70011b04a2f27a9c734550821055f2b23b0479c73633c0fb255"}, {"arm": "treatment", "receipt_refs": ["d98142c843aa749c9489992041d1c14d22c4de21338bbba7ccb27c343d0a5f0f"], "task_sha256": "b7736b292b48bc26155d9928e22fa5036f7d610cca1a9faeef0fedf6a8e51f2e", "verification_ref": "c2c8b786b44dca5dff956f3b0f9b2ea8810a0292c0c28d9782bb0bee2df70c99"}, {"arm": "treatment", "receipt_refs": ["a2bf270f757c5959496c98cd6a9a374ed95732ac7648263e7c63c23df0ec38b4"], "task_sha256": "e4ac9a79a514bfc9cff04d1be0ebbf104e1526aaecbf8dd5ecca23403b82a8f5", "verification_ref": "1dd448c0e174fbbbbcec2c45612f17ce71be32d668cbcc0d9bd7e6d9b7ca1531"}, {"arm": "treatment", "receipt_refs": ["82fdecca7a9f8f4afc28a3d18d83b4483f8c96341f274f1adccc12e867bd67b2"], "task_sha256": "27fe5106eba709a1e256e042e5bd3097c5328f8782324990e50a4632b0af10bc", "verification_ref": "fc699da396e23f88e364ff23ee7964bd51cf00be62a6a7999a3440f4325f8040"}, {"arm": "treatment", "receipt_refs": ["1964309a354ecf58aaf4eee006ef53e043913b111b178cbab48f2665496f0239"], "task_sha256": "eadd99add005654726d41fb8885c96faec61dc2ba4da85b4f209d93314e937cb", "verification_ref": "451425e8d49a9f3bc39d865e7d3fab1a1be8574a97aab7c6b467740d3eba4a82"}, {"arm": "treatment", "receipt_refs": ["d96acfe172e339d29f39c6fea6d8b324fee8aec059fff15fe0430e5127f6faec"], "task_sha256": "74d12c18d2fae166c76f6d521ab9080b160159ee45a879a9428e9d9611058bc9", "verification_ref": "65a44df8013059c260d685836e684b44a1e5cfc7db0159688c0471c62b1885f6"}, {"arm": "treatment", "receipt_refs": ["0cc259fc309e1711997caacf35211faa68a6448589c90a945c13200bc4ab2e07"], "task_sha256": "a2fc73953f4e75744697bfa50c35c10a721b846cab4abe36426e830b1c0c882c", "verification_ref": "054fff59fde2faa0b483834c2153fb4e964f65ceea890d8f4d6e33788ffaabf3"}, {"arm": "treatment", "receipt_refs": ["62812f3db3e8fe6b257c1cc3f05fab1419a59f3d43263cabda38888fc135adfe"], "task_sha256": "3fe72cc6152b850e07f3b32e1f8ece758aa23acdcfd89a76c15f30db1ae613db", "verification_ref": "92489ce5638788eb7c5787e26e1a8ed7b2c5cd193e6268f8b48d33b2ea2bd7c5"}, {"arm": "treatment", "receipt_refs": ["ad610082d8fd05de51a3d5f5db34f73fe775f5f92d6c0c3e8a514fe99a817690"], "task_sha256": "e30c6d6c8b9fcdd7ef5ed090383db088c56619ae1b25b5613c7f47fe3e9a8625", "verification_ref": "d81667739ff075b6564acc6d67fe8a925fd4f97908c1ba20e66a778afcbc9044"}, {"arm": "treatment", "receipt_refs": ["c3097f0dc5746cbc0dabefb49b5299938d167d15edb2b3d28308e2dd07fa79ea"], "task_sha256": "c0bd2d0e80a30e28149addd5ab749028c57ba7a24eabff37f58f02e67f5d74cd", "verification_ref": "69738abdec41c6d2ee2b3c956d9b93c1f9e986f1f4df09b6e02b0fdb40d2f572"}, {"arm": "treatment", "receipt_refs": ["6ece836542e5d64d70a41a42f767c9d8ec633d0e39d075cae02da29529979615"], "task_sha256": "9b0f32ef27dc3b03f9b07c9ba92c89fe6b9b778e66d703edb85e8bdc9036d4c9", "verification_ref": "937ec53d39d952a584c5a7a9fb98f3d1041535a12b8f83ca89b0a04c48f1697a"}, {"arm": "treatment", "receipt_refs": ["6617d2dd965c499107b9accd37caa37dac2ac5c4c7ab1837f00be5c3522f4391"], "task_sha256": "e34661db83ec8a7c879c14ab8427fb9fba0a28456fd94586d2f499a37dedb863", "verification_ref": "1160e40be1cccfbf6a453654803f74e07ef4992a96954c99b63e0ecb47e27a59"}, {"arm": "treatment", "receipt_refs": ["e45099f046591dc2443f0e605f971a9329235038ebdc97841b30be9559ea340a"], "task_sha256": "9fe7304dc376dfbe2925596d5e7c5f4bc2334f3fa69fbcc21948f56371979924", "verification_ref": "1426f361cc930983e5f02ef426b4c597973c27a9d774ea54747317ec8ff29456"}, {"arm": "treatment", "receipt_refs": ["f537da04279307ebcd4accfd620bb0675d1da16ee292820a473a68b798d08c93"], "task_sha256": "8e232531882a394eb64effeab608ae1549cc6a1949ad0db76dc6bf74dc9e0e53", "verification_ref": "8c59cab309770333ccc440bddae61e3291f13d10d5cfdeacb4a0783cdeb293e2"}, {"arm": "treatment", "receipt_refs": ["cac50c7b82a9f60c19bbc0e1faa72630ce607ede83d32f17e8615a3836469a4c"], "task_sha256": "fed77ac22f4e86cf21488aac3867e69f3d5385626b91be5ceb0fff8699d36e4f", "verification_ref": "ba80b9f82c69d9368d1259524846235c08d7144b6c1d644d112176d68c7165d8"}, {"arm": "treatment", "receipt_refs": ["1cb22bf8821de8fb920340ca38e3777235e8fb330ee83b9f637a6a1e88aee80b"], "task_sha256": "72fbec7a95f1be2477888e8ba2a61336b729064816d34872711c0517901ee7b4", "verification_ref": "a6d6e77b61688e1224218151a8e544d8d9ef5d4c2177500a86b7a708a327b8aa"}, {"arm": "treatment", "receipt_refs": ["ca68484fee565e1c70a08ec7ff9556d0f6f31b91699eb684bcd058eeebc0dc03"], "task_sha256": "443a1bf78fdb9c7275787baa44bc2ac14291a3ab36e01ee76f15802f5a4ab48b", "verification_ref": "d4ab110fae91f50b2b76f0e21b2537a90f0dd85b49e5e461c29eea2cc0e2457c"}, {"arm": "treatment", "receipt_refs": ["e13daf66ecc46a829005317f1c3b30787e2ad363f4d3fd331abc1fc7edfa88da"], "task_sha256": "266bec81064b2b7a77770c5c0c8d102f5535ec578c5ec016299475f122a23c79", "verification_ref": "6a8c96986f82f167cc50927b10a3a0459813f4922fa9f68e63566666415f5e9f"}, {"arm": "treatment", "receipt_refs": ["4c508189335cf70dbb191550eeb3a6de5973d660bb2d6dbd6103c1f68df4421e"], "task_sha256": "2e95effc2e9c688deed32c338d1d6da797c75b387c30019fa0c4345b7e40930c", "verification_ref": "467e4133273071f32c5d22f1130799a12d50399fb3af1d08008289d547cc9e17"}, {"arm": "treatment", "receipt_refs": ["d69d1c46fbda29fa0b847c00189009335eb97e51d7c4bfdc0f994fc5ae5afb92"], "task_sha256": "6f70176424880bd418c7a1ff251985991cfe54cf6d5ff80d0dda578b4ab05c7f", "verification_ref": "2c4b6d03d1363bd589aee79c1ef9ee71d5b6f748dda99db8ee66bedff5149516"}, {"arm": "treatment", "receipt_refs": ["ef334f903506b78d7217dfaff109bcfb3f1bb10cbdac1721547bb1524813d263"], "task_sha256": "c4b6e4cff8326b17a86d575f3fae499253cfbe4659181ba6112a07ec21e28891", "verification_ref": "1803cbbf6ab61fa29a2fde95525c2ec0df94704ee211c51883af7e852bb18755"}, {"arm": "treatment", "receipt_refs": ["28ad082556ec7b53314f5bfe4ea1fe4bfafa59c867ee46a7fe44e1300880008a"], "task_sha256": "42fd828737f4bbdce1cfc1a8070dcaf103a3edf15839aff6670060a8a25531d4", "verification_ref": "4591f0daa382dfa8c05ebc7aeaa8963eb197733fe0a23e113fbce2bf4120e112"}, {"arm": "treatment", "receipt_refs": ["ba32621a9ab4981a678468fd357740daa5fbe1787932c62e86db47dadca70c53"], "task_sha256": "72e480883fd7939855992c0321c8321ac78ac8168045b7c1d78510f2aaf44f82", "verification_ref": "abc530a13539a309131963e6fd8631efb0e7361d5842bfb94188f02e1556ba99"}, {"arm": "treatment", "receipt_refs": ["4228fd1249e17e6f276760884d7a3be0f21274a554b8bcf3d0ddb10396de2b91"], "task_sha256": "6eb021ef27afb2adb0b04b39b8207f273f36d1a1165ff423177081ee19feafa7", "verification_ref": "c09b65139c8beec0cdfe0445ea623073d6238d1c2e0aafc67dd2ca06484f7a82"}, {"arm": "treatment", "receipt_refs": ["1c1985518bdf01ddcbd814949964f1ee3c42323d8adabb31d0dd153cbbfc5fb9"], "task_sha256": "a2ccff38bce2de5a0762dc11a72909cb0e390fc17b4fb96fef60ec0ec8331b39", "verification_ref": "8474abf70214864500458459ae2383f2935dca47193edb5813b792cf168975bd"}, {"arm": "treatment", "receipt_refs": ["94d6c07053f37a7ad3fa485c9e96557f6de1bbe08a4ddcaf768de1697bcb705a"], "task_sha256": "0dc7fa848fd78e3bcb3bb0c5877af91aa4455f67dc841d2f00bdabd430dafb49", "verification_ref": "7f8623f73a9a3e0327037912f663f23d9a314304add4eb7c443b39d1d402da99"}, {"arm": "treatment", "receipt_refs": ["a617165afdecbebf9bc934f0bf445831f0564869fc62b78b93152f6916864066"], "task_sha256": "42d808f5ce5e56e96f3e58d5379066bef3ee6af0b9fb05831d5a430873b77ff2", "verification_ref": "3b80b1638a1ca4ae995e3dcb8f66d075064d6c9e5dbb2e3a82c0faeba534afed"}, {"arm": "treatment", "receipt_refs": ["176cfb3cf90f1c74e240195cd62a9e51a81c177bd6a8b63d863266af8d194a3e"], "task_sha256": "00fb81426a05adcc8a0fb94b6e56e05b96ba2ea19265a26c2b7b5125dddb0be8", "verification_ref": "996db97f88be4d2505ef889f93f34486a49b44aab22d1a4c1bbee60b769df4f3"}, {"arm": "treatment", "receipt_refs": ["38208682dc5b1c0dc1e5edd250e0db5f431d5408c81a24d3bccc40af9580ba62"], "task_sha256": "27cdd30710ff25b29e4170bebb57390e5fe474b629d46a34eef79a192e05ae47", "verification_ref": "4dfc3acaded36251d7fe56dae7783c8ece916d4af8010a619b0f7121750a9296"}, {"arm": "treatment", "receipt_refs": ["0661e4f08a4cf84f75d71913ea7fdabe4738b58b46106c9df63194d9bc66b229"], "task_sha256": "7bc4edf00e5ac3c3f1d78fdeae5c8ef2c8c93d18195fa23546daf82fdb896aef", "verification_ref": "0834d795ab21751c0e25644a8c3bc2fe61bf67ac35e0a4ee9c25eece176b2f2b"}, {"arm": "treatment", "receipt_refs": ["e591069285fbdfe0cc57e8d28d8bd0e017f8f863ffb2acfd9ef915075273122e"], "task_sha256": "55acdc04d209fdb7e324a62bc8792c7442002ccec8ff582d2bf00ebb31fc1a72", "verification_ref": "3505ccc0d376e69a05a868795f7ddb2e6d45d0b89df5c76d65d61cebc1cfb09b"}, {"arm": "treatment", "receipt_refs": ["a838cb2b6788d9ddc1ef53ec6c3ae9cb502bfc94cb38d85f3b567ca952ff8f6a"], "task_sha256": "0b7606845fbc817ba8c117b21e680c674bfc48442f10c35b69dd3a086ed802f1", "verification_ref": "dd15fc4d7ff7230f8830a2e3e27126f91b2989ca2e069ccb1079f44a2766c2a4"}, {"arm": "treatment", "receipt_refs": ["b43eafd9c7d77c486214bb57e7f589b9bd1c49d59df32c6d024ac050f3a00186"], "task_sha256": "c356d85bfb50e6254320f886d82dc1e19ef32636b8b97329c81bd2c43316d792", "verification_ref": "27993c3d4230cd3a5d2f668ed0754ed201414d282aad5127b98a42e05827eaf5"}, {"arm": "treatment", "receipt_refs": ["09170acb33eca1a922c7fba94f37093a45141e4d0871a01fbcf0de7513e3494a"], "task_sha256": "4e7e04ca016fa407fbd19d3e6724981cdbd5e8fd0afb9d135bc0dded8697db2e", "verification_ref": "e57373d1f89dcba30590cef9daa974a87b6bcbc5dec94bd54239b2a883d97d70"}, {"arm": "treatment", "receipt_refs": ["b67f538fc2518473fe775f332c772b8fb3e22d48b697d8364cb2be31122c8e7a"], "task_sha256": "8ed5c589b91a2bff0969125f210e0fafdb74d3593e06e7c0b13da03d67290e7e", "verification_ref": "3c2b26a272c0b8efc9091daf6ea58746f5f34bd2d2b6bb64501b82efa1ef7787"}, {"arm": "treatment", "receipt_refs": ["80ce7594166da5d968b804d8c7bb8c79e05b137bd7e4c3388d377c28121629fb"], "task_sha256": "5d2cc41329f8a74999ee5dc2e8395ac342145410ead10e57092360ea7055681a", "verification_ref": "75b3decd93bf350229fc10068c67331ba279550c9d769b6d764765726969fba9"}, {"arm": "treatment", "receipt_refs": ["82e38952dc1be79dbfe6bb2bbb70992044bddf2b7cdf9f9f01789043ba347b2b"], "task_sha256": "fc193185031e09a578732fc3f4bc75bd2fae4a8a90c13c3dacbf685cfd19183e", "verification_ref": "32201ed6969a2bef3d1e23af89e095f3d9940790d730440c2229cc2c57b5e725"}, {"arm": "treatment", "receipt_refs": ["3c241bd412dbdefcb7eea625ff60123f3c0900ed944769bbf118cd66f58ee4cc"], "task_sha256": "a4affe448dca3812c8bb29872f5d89ae3b49764d1b39797cc68c2a96f98aaae9", "verification_ref": "30ca63c08b94638a670d1a8656aae83ff16ba0dd34a6e61e96ab55c27ed7487d"}, {"arm": "treatment", "receipt_refs": ["a4054a2af01d7f5e8dac82f0d7f62925a4f25fe67c965f5b0ebeb7191e44d24b"], "task_sha256": "c1a4a4899f8d472c1034df46ac487aeec6c19f6769805c84371caa101d260f22", "verification_ref": "cca0e02190775d3a2050881ffef4a1db0d55236dce0b171ca79f35abc8ea7007"}, {"arm": "treatment", "receipt_refs": ["15ba184ee06fcb78b1aa133ca74c0ad0fbb33c1997abf3dd6596cfc7b07e7143"], "task_sha256": "f9a2e93f300d9374cd8e32bc654310db7e988a9b3163de9f234c97e52852768d", "verification_ref": "afb9034dfe36b7a292dbda492f7be908306cd69e20ee2873bbb01021f76e587a"}, {"arm": "treatment", "receipt_refs": ["039175f59c3b423da3224310c1f12d8fe3f315e4ffb3c120f8a928ecb7a6f0e2"], "task_sha256": "8ce1f36bad9c922420b7dffc309470d1b97db074cd2fce26d5075ddbebe74a79", "verification_ref": "7bd364ee33402a393cac727ee9630c3ce8c9e03d33f472091caa7aa773e4a7b2"}, {"arm": "treatment", "receipt_refs": ["82852d3a977edb4edddd5fe140c0eb0803803c9b8739c4d7f5b7cdf4f7af1838"], "task_sha256": "8ce0ad065dda5ac0ec2953ba18e0da082e9c412f10df7a999d8fda6491644eaa", "verification_ref": "af1aae1b5049dce9809eec6991995fcea944aa7f1be1bcd7a105eca304a0b379"}, {"arm": "treatment", "receipt_refs": ["e9b126dd1bc3b7426ca4bf34bf03190ab4d8a35387a7d17322d31faa746b246d"], "task_sha256": "ca985fbe7380a108d80b36a8ea35a62b72ee9d2bca6489656f9ea3bf37e81cd9", "verification_ref": "c42b17b0b96d288ec5f6c8a8b34a8f43be71d6e9cce4d482b88a673c964da05d"}, {"arm": "treatment", "receipt_refs": ["e0a66b13760fe1f5645338037a6e1a943da81e0aafacc703df9894835e0628bf"], "task_sha256": "22e3e2afb41600ab8f5beb6b152a7563ba7c59791d1c969ef7e35df5a6ab7ea1", "verification_ref": "d0387f07ecff5409a63381aacb4c41a0350904758de1b978b0f1722acc61ce90"}, {"arm": "treatment", "receipt_refs": ["23d075d82391b1c6974883e5973a65351d6d2ab86e86444b55113530b5f7995d"], "task_sha256": "40d02f69668fe0a090b3acd78f823e9ce3f32f2b289b9264fb730e7132d61edf", "verification_ref": "02a633b2e7fffebd61663bf7d9b244a7a41b26c51f3db9a0be2dfa73a9072cc9"}, {"arm": "treatment", "receipt_refs": ["0b02bf4e5235edd7114ea57212de4e2c201b58343053d933213b8e1cf90c6b91"], "task_sha256": "69fc3c077aa11feaf165eb35ab7b8ec742fa4015bacb4221edd004e0fd7c7da1", "verification_ref": "aba0515858a3ecbed54f36d64aaa9a066848dec6c1c9367df9a5b10e5b5c71e0"}, {"arm": "treatment", "receipt_refs": ["e6b1428ffa82b632356328cf8dbfd7cf093e260b2d02cd8ac41889dff3a5d749"], "task_sha256": "c6a11c87f699c4454ff7b80b7de4768170abf34f0cd048babcf863fe07330967", "verification_ref": "5da1ca93b18aa7b737dcfe0f3084ffde18543a29c5769fb4da1833ef6226d89c"}, {"arm": "treatment", "receipt_refs": ["6a0fcd5454808cc7e9dc91062f737d26099b8f062363aab06712b0c92a95d413"], "task_sha256": "bcdafa3f9252f58f518273930b61146e8bdbc8aac3cb7fd0638e227b84180d97", "verification_ref": "eaed9b39f66bcd99d4518933354aefa3528affb0b42b0c1431a8fa53537da05f"}, {"arm": "treatment", "receipt_refs": ["a9d3f8bb565a91d96df79f1c6ffd98f3562d6237866404032326c86ff7f5aca8"], "task_sha256": "357b0764fe37b0880033823c32bf0625d30af0e128b039a8eb0ca7aa96c95c85", "verification_ref": "4c2017ff992a150bb2c3371bbda55762bf22f43322f49d4120f41be315a5fa15"}, {"arm": "treatment", "receipt_refs": ["7fe9a68fac3647bcd5c0a40d72747e8ed40b4aa8085dda10e786dced81226ad8"], "task_sha256": "83b5edffb26c22d27993d8c489732b48c686d7eb8673e86ad89ed3fab0af12b7", "verification_ref": "e2ff8a5bbfc937a1d855da7a3e46d7e4606284038e9f175df855eeab673503ae"}, {"arm": "treatment", "receipt_refs": ["197d51b0a07b3847a65560669307889b2068e77b5144134e6bf989e6f8ed8353"], "task_sha256": "333c62c3652de577014ce3685d2d6c369f594cedd6745bcc01cf1510e10ecba9", "verification_ref": "a519c258c13ac8c2d65d01d14ffa8547d00d096bcf8c1d4357c85e3e298080a4"}, {"arm": "treatment", "receipt_refs": ["7a7398f445ae9d8ba7f88b7a0042890fda425fd79abddd557be007b4c35434de"], "task_sha256": "4b7936146813d33c5c8c51ef08291f0ff1a80c5b389feef381324ec525ccccbf", "verification_ref": "3d9a3d2c1aacaf4725a36c31f91a6207396f8c744b16e30c12a7babf3189ddf4"}, {"arm": "treatment", "receipt_refs": ["b4081f0cc63d0294f1c40f8a7741da25fa95d339cbd0d4b88ef0616bd5982806"], "task_sha256": "4d7ee8764cd5231fc11d04df691dc5359578f31eca8f5d3e95591f398ea7363e", "verification_ref": "1d03b39c91aea39967bc3ce07a0cbfb24bf3e78b5efeac9a1984fe6ad834d043"}, {"arm": "treatment", "receipt_refs": ["57bfc6558bdfc529a4b9ba73cfe15ecd5c338c01f6261f9875b1e83e578cb69e"], "task_sha256": "74cd65fcb1d30abc5ca496d941341b755aa36eb3b5931fd22c9b7d9ef2f5ab2b", "verification_ref": "e50823f4457d4efb4bd121353d949580a2d5ee31245c9b40e9eea6de1529d5ad"}, {"arm": "treatment", "receipt_refs": ["85563435a5d9a685e4414e630c55d032aa161a2b26b48973b93a8571edd077af"], "task_sha256": "52a50884863027d8f62bbd1f422ee4c6ba68ce83784c1451f61a2164269f4e71", "verification_ref": "4b5e787d4eeed96132befbbed8909c3cb4800e12099190ccb7899921b92b92d7"}, {"arm": "treatment", "receipt_refs": ["3c71ea2eabe35cd2f4ee0032801001373350158bc6c5d566eaae64fdbc3d7f14"], "task_sha256": "fdbbf6f4363ab7398c6539de9e4b72a4dc01523821a57ea2d3195ad96ad74679", "verification_ref": "71e4f17db8b8058d4a81246387a5a471f6c694e161222d550f7635458b6f2951"}, {"arm": "treatment", "receipt_refs": ["bd50c268c7ff3b01062a08503dbe0da6df5dfd552fcfe84c4b4eadaeedc42165"], "task_sha256": "37862455624da8cc0107b427d4f8eacc465a4868311203b229e13349d1e4084d", "verification_ref": "16c002c187435abec2d64ad3dd541bbfee2a40d8967452ec83a977cb625330a3"}, {"arm": "treatment", "receipt_refs": ["aa938a7912ccd1a07d66354692007477a32614cb11a670b627371967a5b8e937"], "task_sha256": "68684087a0a849ed47fc2cb1f64134370ffc2d5e63baff159e52c59360818d35", "verification_ref": "1463dbaa53cd57e7d553c6faf1ca47f1b1ad12d834921fcf1602ac6f80a8a443"}, {"arm": "treatment", "receipt_refs": ["7224fea674ca61ab435de0e317120fb624d7d6d5c25b8796adb419136bc571ad"], "task_sha256": "b637e2df70c5d87652976528b4880dd5ad7da8f41d069b9fe95790c94ce6b524", "verification_ref": "933b49b6d0b46398ca561e4858a9a3f7639e09d791841cfd2e4ad9c9d8f1ac92"}, {"arm": "treatment", "receipt_refs": ["21f7a25cd1f3edd9e60edcd9a9846fc85ebfd02205fc32f1d7ce7abe0cd3e432"], "task_sha256": "396cb101ada7ca8c3c91ae5c882af6aacf64144ef3698726a115804df1063ed3", "verification_ref": "358cea1ddefa927c36b9285b5cb7994c5864a17b5e4dcad9e018c13117ca820b"}, {"arm": "treatment", "receipt_refs": ["b12a114205ad0e1999db3235807275b2196e6a50a8ce09e8883605446d142fbf"], "task_sha256": "6d8137ab755d126cc65528e8f2603246374cbc4c990c3aa3e80c48bd2cd68686", "verification_ref": "fa95164075c8db68ba207a64d0ed201b1301f9c52617ddcfd33a061211668ae0"}, {"arm": "treatment", "receipt_refs": ["76d5c0c391e6e160040771ea9850ef438c80fecb7e81bfcdb079f194c3bfc2a0"], "task_sha256": "59412be36ba7f130411b468c7ec3d453479704a3a350bbbed343b9d3c2fb5f2b", "verification_ref": "552c4dc8ec832dce616980e18b5c7b81df62bde1b40394cfe1ccc2e6d48cae4e"}, {"arm": "treatment", "receipt_refs": ["019e6b7b27732ea42520fa4a32a289224eaae2e1f8018eda20e00db8b9bb9674"], "task_sha256": "80a55dea2d9ece2c3df42c16279378461e8b30a394834c623d8f4f2e479ff7a2", "verification_ref": "23545a1f785add267ec6d360cb6ba1be2176cbd5919ca63ee591568679580e9a"}, {"arm": "treatment", "receipt_refs": ["9c5331b7eefcd1218861762c5b6533ddb622fafd93e9fc17df726770f4b675f5"], "task_sha256": "adab8f4227b6cdcc2e65a1f4f3d0a32d589a2893d766d4c66f2220d1467703f6", "verification_ref": "7be8dec2b9e82bbdd2713ee60aeb19744eebc0951cddef51fd1e072165e103ac"}, {"arm": "treatment", "receipt_refs": ["0e46848662f313bf132e8dd58f67c9d22bd04a58b6362c4c4f63e22c0aeaf874"], "task_sha256": "eecae7585bda4ab6cc55e9478fbc0231fa344ca66ee504992ceda8e2f33dd5fb", "verification_ref": "6c29a4a7318d6125028e667ac3326c0c1d730cd9302f32ca10f1a6934a0271cf"}, {"arm": "treatment", "receipt_refs": ["dab3d56eb68ff6f2c5196232c17d0813eb0c958b027bd50b011d84e81303c433"], "task_sha256": "201e1e0fbfa29a9b229963920685aeb22bb0ad439665504b3a7162ff19d9b417", "verification_ref": "eae90f31fa82bb4fdc53f815329d61db948a99abe6c39989a27b0a691fb699b7"}, {"arm": "treatment", "receipt_refs": ["2728a959932f8ab968a6905b6a4fc8d07664443916b83ef40676fe3a880fdf12"], "task_sha256": "fcd499c930b498454c45477a886db23758c8828d9deb22d5450f48f696d3d886", "verification_ref": "16119cb4be0279fa3fe5ab2b8a35fea3847a54d7db9696f23656e4a2df89c689"}, {"arm": "treatment", "receipt_refs": ["cd0dd1b624667df840961dfe02c00cb1859b75cfbdb0a06dcb4fdb569a84f9fb"], "task_sha256": "2adab41ef8890039e9026b9213bc60ba8d3fd3b2b28dbebdc52183634ad9a607", "verification_ref": "a75d9538d5c37b506c9c4de5b35d9598813bda44db876d59f6f7953567e2da49"}, {"arm": "treatment", "receipt_refs": ["f34fbea7d5502061d8c7bdc88fc2765ed860524c31babbfd90e11da6b36d85e0"], "task_sha256": "d32cf6de2806a9c573cae0d90512e75cd557d2d09f6ed9ed3fa8becab87f8ca0", "verification_ref": "091afb5bf3bc5779b83bc8459688406a6cad7ae3e6e439f7f4f579eab1769774"}, {"arm": "treatment", "receipt_refs": ["1d10610386f3cff0af858a2a34dc3ab25ec85b68f99c7f9366aee44ee5e104db"], "task_sha256": "8f09dfac198bae1fb478e62d7a42a50f5db1202a4bcdf46f54c1e9fd149e8f99", "verification_ref": "578b2bf30faea6cc52029ab4016d8493046c3bd16581b212a84db67f5cae85dc"}, {"arm": "treatment", "receipt_refs": ["0fea9c53d23e2a42832833bddf8b5fcc3cf569fa5004cc64a7a8f794bdcd095a"], "task_sha256": "35830dec0775d3126eb2a453344d2843806a472278419a0ff30776e29388308e", "verification_ref": "2b96a3e0cc8d68f252acd2f98a6abf3e19e3744d1cbff1acdfba7e1105db02de"}, {"arm": "treatment", "receipt_refs": ["4b5d88c9acd7e15f0d3e51df39c5c7ff3623cc127d27b4b46d8ed0e2f0dcc8a8"], "task_sha256": "bc182e2d6dbb4c5386b761cc2e82175600da6d7e20e78deeba326a2c28633dc0", "verification_ref": "dde3a3937bb0465cf0cc4b04f98188bf20e77b2af2d22f170375b628845f71fc"}, {"arm": "treatment", "receipt_refs": ["5f5de99d353d3b966f44a6ccf43e5dc0a84a4aa0dd601a9c11bb133d064f351c"], "task_sha256": "839d2bb100cc1318623e08cad366a1b94d8d8a89f0447ff0f62025d5fcc6f6d8", "verification_ref": "495271dd28ceb9cf718be46cf67884fd074784a80d9d08b2fdf2e6e51dd3431d"}, {"arm": "treatment", "receipt_refs": ["395658653749e1414e310a0feb58c12d7fede186b8918ff62e5575414a3e3de2"], "task_sha256": "8e0c3182ea1ce7fb8bd7f9fa713af4e327d6add07f0aad03bbfbe10fc63496cf", "verification_ref": "78a04bf42d26c929b7709d330d4eb4ed8502d78eace8337aa47baf138a62f1a3"}, {"arm": "treatment", "receipt_refs": ["47a0415d137c2855eb9b906954ea8071ef2ae6f02400f824caf69dbe94890771"], "task_sha256": "ab10745df44b299d3b71851e90466b190b238e7fb3b5d667a811b66f83d25076", "verification_ref": "41b4bb5e1a0c9f896d6de69a2dfbdbe016094e305f23d0f5cf8e257704cba1bf"}, {"arm": "treatment", "receipt_refs": ["a4ac2f1e33de4ec5a4acadecf46791cca463c2876ed62d05d5764f06676fb894"], "task_sha256": "b8e8c0408db65161457981bb4fc60c5d0fdb3f3a47ef63694729e88f0aeac0ef", "verification_ref": "2f98c722bb3924b61bdb3abf193006f62252c939ffa9bd0593358bb175614be3"}, {"arm": "treatment", "receipt_refs": ["cb1baa4dc5855dfa5123be9b2e768d9a2e33ae604ed4d04d8f5ee28a96c8a1f5"], "task_sha256": "626ca525393dbc1c83f3751f74861205056af4264f770d1134173423a0ca6ad2", "verification_ref": "12686b4b8814c91eac3c8579ea1d5fabe0aff36e4de14bb4b2326518a87ed334"}, {"arm": "treatment", "receipt_refs": ["dc9e4201c80dcb4e903d179bc82f2130290caeb7add0f643520f4e6bfd22f1d5"], "task_sha256": "38816e1a0552e4169aa1e3127bae7e9ebf8b0f8ea99e868486fd630b409dc4cc", "verification_ref": "d470c641e77c52f012747500e9cf03198d7ceed47b1de7fbf0cba6cd23a588bf"}, {"arm": "treatment", "receipt_refs": ["0f2e34eb673328adfa6ef9cdfad97dcce393cc32812f505138fcc9e8f52e225a"], "task_sha256": "7044b611e2e6bea0b4c9b50d5e55c10eb8bf09923b0ad06f42b2414916f33f6f", "verification_ref": "d8cc66269902dc16dd6c210f8c8f9335aa6d0e6368c33bf7e52cc0e7808793b7"}, {"arm": "treatment", "receipt_refs": ["6ae887fc237b8b379bf6a438141b7fd08b1fc495eb605efb3d9162d596d65bdc"], "task_sha256": "aec1146254e3a385a514d2478c9ac256e164fa4ed21ebc2fd08c00c8f7b4ebe9", "verification_ref": "541c210ab815bb39b223d9ca4d7f5196685c1c86d0f81bab7a652511abf10008"}, {"arm": "treatment", "receipt_refs": ["688137e0647730a4343088ad3429867121a9592ee944297666af5431791fe905"], "task_sha256": "7d63f222e4c55b580b65d407cb2e4d156db801cf2d77a9090a0e2909f1f620da", "verification_ref": "0d216c1740563cc97af2bbce74b5c277ee521a3fe6d1709bb804530e4eb7e266"}, {"arm": "treatment", "receipt_refs": ["d5e59af328693880d14844d914bc0a3600e68f8cb7b80ddf00bd85869cdcbf9a"], "task_sha256": "88b4da2f66b4b9b0679f215bac0f19533b0b0831fe4ca90aa86842b8988cb2a9", "verification_ref": "cc250e93b3338f7396c8de5fc6e3e3a15f7c4108738449ec4e4f2c8d986c166a"}, {"arm": "treatment", "receipt_refs": ["9c930713e195b0924282a97431d0f1a645decab67d318b2a1a75251102eff9d9"], "task_sha256": "7031f79d7fb6653411508ac1b06d98458062c423c0836bba6d8b3f4c8978b3c6", "verification_ref": "c45c0d0d26795702e4cb5b282d5a08a5316eba5429f9a565bff68219661176b0"}, {"arm": "treatment", "receipt_refs": ["e21ee31c396e7c976c13ef77574b1d2149108184570ba80f1ed45f911b89c556"], "task_sha256": "07f6f57e38ca1b707c748fee5ee855d8570613dc3d641e7b1a35acd34f8e31a4", "verification_ref": "ae1835a2e26a8f934bfe581b80f71ffb59782050da22ea4e8acb22dead7bd603"}, {"arm": "treatment", "receipt_refs": ["a6f2ed1d411977245b52648593a1d5deaaa59553021933e1034b6fc1255807ff"], "task_sha256": "7659d47cf0f63c08d36fdf2067f85eadd2b0981d78bde19dd15a8520ec124978", "verification_ref": "f356986a261a8f56e176b54ecfb6540bc013c365e647f19edaaf7e0c0641658b"}, {"arm": "treatment", "receipt_refs": ["df1eee3a7479b675b7a122d9bcac5db8d6d97280afd624e67fe3d3f7eecd0ad1"], "task_sha256": "a76eebfa743d8d5f8cf7f0e34bc06b7e350569a96a58a1b9e172fd5a5eb77eeb", "verification_ref": "c8a61934497ae53a9bbd7099b7d567e4f3489bb4792bb7f3bd8e0c5fa3b6b4d0"}, {"arm": "treatment", "receipt_refs": ["e82c22d06c217a714dc6973a7e1a8fbd288474d16d140867ee624157a889da67"], "task_sha256": "40e17fff94c25a14ec87af9e83aac131be04f30a919b48352603553c79237175", "verification_ref": "f73aff29b15e4d011f7015efd3de7d14496b83c07d1e81d4697223eef0effc32"}, {"arm": "treatment", "receipt_refs": ["6c83ec6c98a2b7dea12dd590eaeb712aafb15564ae9bc0807a267b9d7b4a8c3a"], "task_sha256": "d24f24fd4779bcf425998a47a4f3560b710fef426626e59f910a28760b774e69", "verification_ref": "71c5ad779e6ea3c8e1b070764df2cd7eeff602ed1db9d3cb81cd59bfbec5fd92"}, {"arm": "treatment", "receipt_refs": ["973be92384132c21c71da632e79160d2dc3b58915d19b83cd572909d86b90382"], "task_sha256": "a9255ce68456870305396af18dc101f29a7c4d44ce2667c6be55a4f7312d0cc8", "verification_ref": "8b0aa377789e49b113d8c6718da40cef613730522efd009a7f75de338476e606"}, {"arm": "treatment", "receipt_refs": ["fae720a142d52aa5a11eafc28f1032a0472f02bad275d5eaad145bf7fc781601"], "task_sha256": "8f8cbe4f45948fcb04ba3c30a0c915c3923a8093e0eebb965e0b4a4d9e1d711f", "verification_ref": "792bd0c12f55e1390c99a857cd359ec406f23780fe9783eb63cb2b778e2cc259"}, {"arm": "treatment", "receipt_refs": ["cceaed0c3414f70425b398ebf6f47fac6bed3f5bd73527cda237a3709ec0650f"], "task_sha256": "9a0e817c865755089cf58dd0aa0171fe558c40d82cb1e94477aedf22bab89880", "verification_ref": "928d2ffe7e303faaab9bd516872dddffdc820b7e715286c2ede88a0349567456"}, {"arm": "treatment", "receipt_refs": ["55a4f04e35b342607a00fce39c025845c220c91bccd498817f8fdb71f37c55d3"], "task_sha256": "fe35392a78a17a094a48448951db1f8e8115edf017df265020e31eaae3ced5ec", "verification_ref": "c9c253ca51319c3ea0e98d0f8ee46672f7ce5befc5dae457c333968da043a0ca"}, {"arm": "treatment", "receipt_refs": ["be206f66b4bf702df6cd1fb9600d634e22372a891a32b75a901427bbde443598"], "task_sha256": "f93b02d73fcf7047ba969b76b2c4e90ec60c950adbf1bbd67bb89143d14728b1", "verification_ref": "14c9074ee6b252fd6c6be5654b378bd88a88c15976e3540816c6bb06b182984d"}, {"arm": "treatment", "receipt_refs": ["9d3241f95a5a3e55cb1cae5893be01636c74ed1ac8683daf43d70a7990a675bf"], "task_sha256": "a8d00362ac9132886d77f91b88ba15d38c386fa8f47b493a9aaccf7f0d17cb64", "verification_ref": "47a819aac626e2a3f17a43d41e744f036d5e69fcd88eb398de781fb5131a1c87"}, {"arm": "treatment", "receipt_refs": ["f5b9813cb310f06f303a3f041fe5c7b8bf42cb6139dc5cd88525e074b18c3ce6"], "task_sha256": "4fd9bde1604d3043df2923121e52f15eb215f2d5cc6837f615ba3f208e49227d", "verification_ref": "0cf21461d0dd18c8f0694750d98b49158a9b819a39181ff2a1f9819d2102b527"}, {"arm": "treatment", "receipt_refs": ["e5dcfd243c8a0d9c90f843b8a86e7527e950b6ff41cde1748eea6c16a0f47f2d"], "task_sha256": "10064b913a58eba0486b95eadc5eb0cd3afb92d14dc5348458376362e0244ac6", "verification_ref": "8b8b950262b727eeee88dbaad56bf29f79bcf7d95e64b22a906ca6b300a97f9a"}, {"arm": "treatment", "receipt_refs": ["2a7fe69d28f30d9a42c7fb6a74dbe96a7343e15a0b19bbbb7779cda5625dddf6"], "task_sha256": "5b7018bbfc315feca338b079bf7c1e911a43f81c256345e2f6ae4a5d06deae44", "verification_ref": "231a37590358611521682bce107ec50d8939dba24d8d29deaf1cd7b554deceb0"}, {"arm": "treatment", "receipt_refs": ["b3f89874932d8d9513101522f448575f07ffa9329da8993ff43c42b858282a8b"], "task_sha256": "b412a361fe09ac6ddb086107ab223e49a5c95c91f28d950998b195ea3ce69b9d", "verification_ref": "0a2e47e2f7a5a7df5812bf2820dd202da263b43767f25d117ccb272aa115959e"}, {"arm": "treatment", "receipt_refs": ["c1a39ff37b00dc5ea49580fd31c1d8fccd335852f278bb585009267b9f1479d5"], "task_sha256": "7c31ca84a1f2d1013ff3987f3dbc21d4497a6c8f4c1fc360b3e899b0a63cf958", "verification_ref": "3ca1fa59055c9138e728ec9b85a0db9403012f96ea3a03b1ff3b710af69c72aa"}, {"arm": "treatment", "receipt_refs": ["b29d851f237c7b1c129c765601d3497753ef0070f21d588cd701f310618cc61d"], "task_sha256": "5cfb2acd8a695165cfc954aa62c507c1008b34a98e68066a61133826c6b638e8", "verification_ref": "7223e9e432c607ec8c1782d1d9223d60defc6d2228c82b38b7fc3cb1d401a0e5"}, {"arm": "treatment", "receipt_refs": ["9350ca4478f0ad6c521672b54ed6851493c78a0569781d3442f3342540f93576"], "task_sha256": "0f77621249c5ffb373aafd67ed106df81600e8cab9fdec032334d46621749e0f", "verification_ref": "e572fe4161986f9e09a8d7d0dd8b4ad16990b388588a10427bb6fedbaceb8023"}, {"arm": "treatment", "receipt_refs": ["3bb065f29a1eb17e024abc8ff691776b2f6292e7619d4bbe682fab7752bc3a77"], "task_sha256": "c2d3ae55e88f5a594cc8f47bb244020ccbd418f21a2bdaf7930fc4ee245cee26", "verification_ref": "68a107e55b69bb5c56523a825b3c5778e406c18c4aca98c532d6538f8b6b3d5c"}, {"arm": "treatment", "receipt_refs": ["105eac763f45091509bb79df0364a461b70d5ba5ab64a358fe37530464b96b5d"], "task_sha256": "6324c8ab68d010ba36c7645b753492691fad6535b5e938580bb5f2ca8463fe10", "verification_ref": "f063556ef89fa26ea727ecd27f9364da2c19607ee646efafa1b6719f77c77d80"}, {"arm": "treatment", "receipt_refs": ["f42dac26a8a5570d77d7d375ca59dbf14bcbe870b80ac3b67bd934b914fbb669"], "task_sha256": "f5c080bcc15bc333d45cf0d12cad2b9f61f6efd45a3de1137131cf53ce0fd92e", "verification_ref": "3f8f5de72d1653d4cc078b312c68c8966d1a96a2a00e898381abb7857a6d8aed"}, {"arm": "treatment", "receipt_refs": ["e4976d30f0f3e75c12d2541a16e5decec7ec649a87b25ecf81765d57d79fa691"], "task_sha256": "ee297e7cfa2195db8cfa7f7754232c63861c60f1c09c419f54427105d30b12d9", "verification_ref": "99938814e9bebabc94ec3124586b1a517c9ef7f2d57bf949c441ae25c1e43e10"}, {"arm": "treatment", "receipt_refs": ["2486523a6e5c9514ba6446602fdea7320e91cea1d13df33e560c96bac1dea23a"], "task_sha256": "8da6bfd1ed2eeaac9e3fefc89beeadd78e900d7269271b47c2962afee689398d", "verification_ref": "eb86a710314f896bb8c692971f8681ac4eb77235c353920ddd9de19f665a2c68"}, {"arm": "treatment", "receipt_refs": ["10c96a01dd1baa81d24ec5cecc7bc0d622d8da80adb35f6bc2a3a278ab9ee2a5"], "task_sha256": "6f4858f6f7a717b4e33b2753aa9f1a97d7bbce33586456728a3c16b6c742c2b4", "verification_ref": "66e52cdd2fce082a895177cb28d8919b5590608d4f637cdf352fb985c4fd6898"}, {"arm": "treatment", "receipt_refs": ["d41dfce75052fdf101ef3870e15721cdcaaf0f7a41e057829babc03661d93885"], "task_sha256": "ff24033ab09b78125c54b5903bb9c9f5cf46ffb9661e2fb5d972d4b094e77ec1", "verification_ref": "3c4c66cfb82e57cfaebc828216daf68e136abb7a01ce4ddfd328242e5e35ccdd"}, {"arm": "treatment", "receipt_refs": ["2afd4fb38a69610d9fbe7b2cac13faba5d2a5951a7900595aa782397afba1c73"], "task_sha256": "e452d52180c378ed047850760debfc329aa26ae154273ead40084fefeabb53bc", "verification_ref": "f826f77331a9e7bb9eb8a5dfad5790d49eeb4279f3a215df1a3179a3c44c30df"}, {"arm": "treatment", "receipt_refs": ["0e7c1019096b3ecc30b8f97f2953f75f1eb13bf5b94bd5fe548ec6829487ebdd"], "task_sha256": "7253502d472e3dc845c7e74eef9b07df0c9b4c7f19a6e2bc3b026a6e53c9dae3", "verification_ref": "54fff3bf714ec4c658a22f61bca72366688d1dc11e7d3e0f3a8398eadd25ba33"}]

Limits
Artifact contents and file changes are not included in these normalized records. Resolve receipt and verification references in the originating run; grades alone do not describe edits.
Access ceilings, spending permission, pending approvals and activation state are not established by this summary. Consult the exact reviewed plan and installation record before further execution.
Describes supplied records; this command does not authenticate referenced receipts, worker conformance or grading evidence.
Only observed tasks are checked. Entire missing pairs cannot be detected without the reviewed plan's expected cases.
Different cohort bindings are never pooled. Repetitions lack a pairing index and are rejected rather than counted as independent cases.
Partial measurements are labeled as known subsets. Resource differences do not override task failures or establish benefit.
Synthetic and replay records cannot establish real model value. Invocation is not evidence of causation.
Confidence and value verdicts require the existing reviewed analysis. Supplied receipt accounting is descriptive; recurring fees are explicit scenarios, not incurred charges or a demonstrated benefit.
Canonical campaign: 141 trials; 141 normalized primary trials; 0 normalization gaps; 0 auxiliary trials.
Canonical analysis includes its frozen conditions, repetitions and auxiliary arms. Descriptive tables below cover only normalized primary trials; they cannot replace the complete campaign or cost ledger.
The canonical verdict is the assessment service's recorded conclusion, not a new toolkit qualification, independent attestation or release approval.
````
