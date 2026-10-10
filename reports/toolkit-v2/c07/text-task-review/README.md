# Text trial stopped at the Codex response-schema boundary

The current text qualification did start a real managed worker. Its first model
turn failed before producing an answer. This is an integration failure, not a
wrong candidate answer or evidence of benefit. The service stopped the campaign;
no holdout ran and no admission was created.

Source: `a9ed7b91a76ae1ffc3ace75d4255ec8c314d19b8`, verification digest
`ca838bb3a0fd1f22e0098a2fe383cfc6c364481f6550ebc13fa85988414a2464`.
The exact reviews use the existing September 25/27 delegation and the original
`onboarding` ledger. They do not expand cash or credential access.

- [Paired inspection](pair-result.json): both existing immutable workers passed
  all 11 boundary probes, with cleanup and restoration of the stopped proxy.
- [Boundary assembly](boundary-result.json): current task profiles have reviewed
  conformance. The earlier preparation rejections are retained beside it.
- [Qualification](qualification-result.json): plan
  `plan_f95d91af80544ceca67dd00f78f48922`, report
  `fit_c11e3ad4452940feac6fefdf1b0598c5`, insufficient evidence after one failed
  screening execution. [The exported report](report/report.md) preserves that
  outcome and unknown provider usage.
- [Separate diagnostic](diagnostic-result.json): a fresh screening-only pilot
  was explicitly capped at one call, then cancelled. It cannot qualify a route
  or calibrate a campaign deadline. The [observation](diagnostic-observation.json)
  classified the transient error as a schema rejection; the configured rate-limit,
  authentication, permission and model-unavailable patterns did not match.
  Only the classification, byte count and hash were saved, not the error text.

The adapter forwards the recipe's general JSON Schema as Codex `outputSchema`.
The text contract has a root `oneOf` and dynamic field names. OpenAI documents a
[restricted structured-output schema](https://developers.openai.com/api/docs/guides/structured-outputs):
closed objects with specified keys and required fields. The AEEP contract must
remain unchanged, including its local validation and independent grader.

Both calls and preparation costs remain charged. After the diagnostic the grant
record contained 9,759 operations, 2,842 model turns and 107,983.35905627976 elapsed
seconds. Its cash ledger is `0.0`; missing provider usage is not a measurement of
zero consumption or a billing claim. Both runs confirmed proxy restoration.

Next: implement and test an explicit Codex prompt-schema mode, renew source-bound
task-profile conformance, and freeze a new plan with fresh cases. Do not replay
either completed request or reinterpret these failures as successful trials.
