# Check workers before a live comparison

Confirm that the reviewed workers can run the intended task and supply the
declared measurements before spending the comparison allowance. A successful
software fixture, network-denial probe or model-catalog read answers only part
of that question.

1. Check the task-owned model proxy's identity, running state, exit code and OOM
   flag. Verify its private endpoint with a positive connectivity check. In the
   October 19 study, the reviewed proxy exceeded its 128 MiB limit during startup;
   its measured peak was 189,833,216 bytes. A reviewed 512 MiB/no-swap limit passed
   readiness. This measurement applies to that pinned image and environment.
2. Preserve the working task profile when changing recipes. The editing recipe
   passed with prompt output mode. A profile copied from an older structured-output
   experiment lost that setting and failed its first task; its exact backend error
   was not retained. Both corrected arms used the passed mode. This observation
   does not establish compatibility for every structured-output schema.
3. Verify both isolated worker identities, policy, candidate difference, pinned
   model and supported effort. A changed profile needs its applicable boundary
   evidence. Reusing unchanged images does not by itself verify a changed profile.
   Protected sign-in remains an operator-terminal operation; never inspect or copy
   authentication state through agent tools.
4. Match utility dimensions to the ledger's native keys and check their provenance.
   For example, this study emits
   `model.openai.gpt-6-astra.subscription.input_tokens`, not `input_tokens`.
   Protocol counts can be present while their evidence remains
   `provider_report/self_asserted`. The strict utility requires observed or verified
   evidence; changing a name cannot upgrade trust. Keep unavailable guardrails and
   report an inconclusive result when their requirements are unmet.
5. Freeze the cases, thresholds, exposure and measurement interpretation before
   holdout. Distinguish required-use qualification from optional-use comparison.
   If a preparation defect appears, preserve the failed campaign, incurred costs
   and uncertain attempts. Use the existing recovery procedure and fresh cases
   where required; never replay terminal operations or tune thresholds to results.
6. Check host free space and Docker usage before provisioning or snapshotting.
   Keep the 50 GiB host reserve and the reviewed campaign envelope. Remove only
   authorized, verified obsolete resources; preserve unrelated work and backups.

The [qualification report](../../reports/toolkit-v2/c07/edit-study-prompt-20261019/report/report.html)
records 141 successful required-use trials. It establishes bounded task
correctness, not optional-selection value. The
[current state](STATE.md) identifies the running comparison and its one-shot
driver; use those records to resume without repeating work.

The [managed evaluation guide](MANAGED_EVALUATION.md) describes the existing CLI,
canonical receipts and report export. Keep provider-reported tokens, independently
observed wall time, task correctness, experiment costs and billing separate.
