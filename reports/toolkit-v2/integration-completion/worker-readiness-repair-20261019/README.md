# Worker readiness repair — October 19, 2026

The pinned workers can reach Codex again. Their shared model proxy was OOM-killed
immediately under its 128 MiB memory cap, leaving its correct private IP with no
TCP listener. The repair changes only this existing task-owned proxy's cap to
512 MiB, with no swap. It retains the same container ID, image, networks, access
policy and filesystem restrictions. No host Docker setting or authentication
state was changed.

## Observed cause and repair

- [Detailed readiness diagnostic](readiness-result.json): rate-limit RPC failed
  with transport classification, without explicit quota-exhaustion or auth flags.
- [Network check](network-result.json): expected and actual IP both `172.18.0.2`;
  TCP connection refused from a no-credential read-only control-image worker.
- [Docker state](proxy-state-diagnosis.json): exact proxy exit 137, `OOMKilled:true`,
  about 0.3 seconds after startup. No raw logs were retained.
- [Exact repair review](proxy-repair-review.json) and [result](proxy-repair-result.json):
  512 MiB cap, no swap; TCP connected, CONNECT 200, TLS 1.3 verified. Measured
  proxy cgroup peak 189,833,216 bytes exceeded the old cap. The cap is retained;
  the proxy is stopped between operations. New diagnostic workers were removed.
- [Both unchanged worker readiness checks](paired-readiness-result.json): ready,
  pinned `gpt-6-astra`, reviewed identities matched and capacity reported 17% used,
  not exhausted. These are provider capacity claims, not task-cost observations.

The memory measurement covers this proxy startup/health operation. It is not
whole-toolkit overhead or evidence of token, time or money savings. The exact
container/image identity and old/new caps are in the review; failed health would
have restored the old caps. Those old caps cannot support the observed startup
peak. The [OpenAI App Server documentation](https://learn.chatgpt.com/docs/app-server)
defines the rate-limit RPC separately from thread and turn execution.

## Task-profile correction

The fresh post-repair editing plan `plan_16fb057af234452e91214c6829348d29` stopped
on its first turn without an answer. No correctness finding follows. Its terminal
report is `fit_0fedf41c912d4817b8f4cee770429740`; no task was retried.

A [separate public-input diagnostic turn](turn-diagnostic-result.json) succeeded
with provider token fields. [Definition comparison](editing-profile-regression.json)
then found the editing preparation inherited pre-D57 profiles and dropped the
verified `output_schema_mode=prompt`. Its dynamic file-key output schema was
therefore submitted through Codex's restricted structured-output interface.
The configuration regression is directly observed; the backend invalid-schema
explanation is inferred because the failed task's raw error was not retained.

[Fresh corrected profiles](../../c07/edit-study-prompt-20261019/profile-correction-review.json)
inherit the passed D57 mappings and assert prompt mode in both arms before
preparation effects. Their images, candidate, host, model, effort, ordinary tools,
permissions, task/grader definitions, counts and acceptance thresholds stay fixed.
[Fresh paired inspection](../../c07/edit-study-prompt-20261019/pair-result.json)
passed all 11 probes per worker with cleanup. New boundary identities are recorded
rather than borrowing the old profile's identities.

The next qualification is `plan_a26f0d5197c849ec86aed1b7d2969579`, seed 2026101903,
with 141 inputs disjoint from both earlier failed plans. Value seed 2026101904 is
reserved separately. The exact execution review is
`9e1e51a77887a85a19ca56ccb60e80265e9d801cd9e58b0245828c99b78cae12`.
The training-only builder uses only its 28 training inputs; generated source stays
inert pending its exact review. None of these checks supplies optional-use value.

All work uses the existing grant and counters. No production source, upstream
version, dependency installation or image build changed. Existing full software
verification still binds source `d2c406f`, digest
`d05541e90d2e200ba1ea61b4169a8ebcdf62fd96217fdbe35a81e42accd4d1b0`.
