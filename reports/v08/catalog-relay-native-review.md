# Native catalog metrics relay — September 26, 2026

The opt-in relay captures bounded, sanitized supporting observations from the
pinned Codex process. It does not establish complete native discovery evidence.
No subscription model call or live grant operation ran for this validation.

## What ran

The [exact implementation review](catalog-relay-final-review.json) binds the
collector, adapter, launcher and tests to source
`180806bb74076753dfaabcfc083c160ba4b79ca9c1762a8e0641ad8b936598be`.
The collector uses stdlib HTTP and the existing worker stdio connection. It
retains four declared metric names, numeric values, bounded enum attributes and
a hashed skill identifier. Raw export payloads, prompts and other attributes are
discarded. Snapshots bind to an opaque execution scope and canonical event digest.

Two offline probes used the real pinned Codex binary with a local synthetic
Responses endpoint: [explicit skill](catalog-relay-native-v2-true.json) and
[ignored skill](catalog-relay-native-v2-false.json). Their container had no host
mounts, credentials or external network. The synthetic response chose no tools;
these were protocol checks, not tests of a model's skill selection or task quality.

| Observation | Result | Limit |
| --- | --- | --- |
| Explicit skill content | Injection metric and fixture content observed | Explicit invocation does not test learned discovery |
| Ignored skill | No injection metric; description reached the synthetic request | Absence of a metric does not prove the skill was unavailable or unconsidered |
| Catalog counts | Host counts were six; thread-context counts were zero | The description still reached the request; counts cannot prove candidate-specific exposure |
| Collector access from sandbox command | Actual collector port denied in both probes | Applies to this pinned offline profile; authenticated policy needs renewed conformance |
| Clean process exit | Final snapshot retained after stdin EOF | Export completeness remains unknown; closure is not delivery confirmation |
| Coordinator discovery fields | Exposed, retrieved and invoked remain unknown | Partial metrics cannot satisfy native-catalog completion |

The [corrected immutable fixture image](catalog-relay-image-build-v2.json) then
passed the actual worker entrypoint and adapter initialization tests, followed by
the two native protocol checks in the real-container suite. The first snapshot
had a non-executable launcher; that [failed attempt](catalog-relay-entrypoint-initial-failure.json)
is retained. The packaged Dockerfiles already apply the required executable mode.
Neither image is an authenticated or approved live comparison environment.

## Required before live use

1. Review the collector-enabled worker profiles and telemetry configuration,
   including effective network destinations. The pinned binary requires analytics
   enabled for this metrics pipeline; the local collector setting alone does not
   establish that every upstream destination is disabled.
2. Rebuild both reviewed arms with the exact collector and launcher, preserving
   their reviewed candidate difference. Renew source, identity and post-login
   boundary evidence before any campaign turn.
3. Obtain supported candidate-specific observations with clear semantics for
   exposure, retrieval and use. Preserve unknown values when observations are
   incomplete. Do not infer negative facts from missing batched metrics.
4. Execute authorized native-catalog trials and reconstruct their records through
   the existing campaign verifier. Scripted responses cannot satisfy this gate.

OpenAI documents skill-injection and catalog-count metrics in
[advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)
and progressive skill loading in [skill documentation](https://learn.chatgpt.com/docs/build-skills).
These descriptions do not promise complete candidate-specific discovery telemetry.
Earlier [protocol findings](native-catalog-telemetry-review.md), including export
loss despite a successful process exit, remain applicable.

Final compatibility, package and real-container results are recorded separately
in [validation](catalog-relay-final-validation.json). Release readiness remains false.
