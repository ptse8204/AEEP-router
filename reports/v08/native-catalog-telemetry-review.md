# Native catalog observation review — September 26, 2026

Status: local metric delivery, trial tags, explicit injection and a scripted
implicit skill read were observed in Codex 0.154.0. Learned discovery and complete
plugin-use observations remain unverified. No assessment worker profile,
authenticated environment or live authorization was changed.

## Offline results

The final probes used fresh containers, no credentials or host mounts, and
`--network none`. A local response stub returned fixed protocol messages; no
real model ran. Synthetic token counts are fixture data and must never enter
assessment accounting. [Validated records and program hashes](native-catalog-metrics-research.json).

| Check | Observed result | Scope |
| --- | --- | --- |
| Analytics switch | Local exports arrived with analytics enabled; none arrived in the disabled probe interval | Required setting for the tested configuration, not a universal absence proof |
| Candidate available, ignored by stub | Skill description reached the local request; full-content marker and injection event were absent | A deliberately scripted control, not learned model behavior |
| Explicit skill input | Full-content marker reached the local request; `skill.injected` reported `status=ok`, `invoke_type=explicit` | Positive evidence of instruction injection, not successful task execution |
| Scripted implicit read | Native command completed with exit code 0, the tool result contained skill content, and `skill.injected` reported `invoke_type=implicit` | Real host/tool execution driven by a scripted response, not learned selection |
| Trial correlation | Selected metrics carried the supplied `service_name` | Can bind a future collector to an opaque AEEP attempt identifier |
| Catalog counts | Metrics distinguished `host_world_state` and `thread_context` | Counts cannot be pooled or treated as a candidate-specific exposure list |
| Collector access | The sandboxed synthetic command received permission denial connecting to the collector | Tested command path only; other integrations need their own boundary evidence |
| Failure and shutdown | A thread-start counter also appeared after failed initialization; probes ended by SIGINT | Neither the counter nor process termination proves successful setup or a complete flush |
| EOF shutdown | After a completed scripted turn, closing stdin exited zero and delivered the implicit metric; none had arrived before EOF | Positive shutdown delivery in this pinned offline profile |
| Collector rejects export | HTTP 503 rejected the batch; Codex still exited zero after EOF and no metric was retained | Clean process exit does not establish successful export |
| Killed host | The stub received the full skill content and the turn completed; SIGKILL before export left zero metrics | Missing injection metrics can coexist with known injection |

The final user-skill records are
[available but ignored](native-catalog-metrics-user-skill-false.json) and
[explicitly loaded](native-catalog-metrics-user-skill-true.json). The later
[implicit-read evidence](native-catalog-metrics-implicit-research.json) includes
actual code-mode command execution. Requests omitted the top-level API `tools`
array but contained tool declarations in prompt context. The earlier inference
that this meant no tools were advertised was incorrect. The collector stored selected numeric values and short
reviewed tags, not request bodies, tool outputs or general log events.

Earlier attempts retain their errors. Synthetic-turn v1/v2 optional probes
reported the intended analytics flag rather than the actual false setting;
those observations cannot support an analytics-enabled absence claim. V3 and
later read the generated TOML setting directly. The final program is preserved
as a [research artifact](native-catalog-metrics-probe.py.txt); its fixed seccomp
path refers to the [reviewed offline profile](native-catalog-metrics-seccomp.json).
It is not an installed collector or a release test.
The preserved programs name historical output files. Treat them as source
attachments; any repeat must use a fresh output prefix and retain prior records.

The [killed-host observation](native-catalog-metrics-killed-true.json) establishes
a concrete loss case. Absence of `skill.injected` must remain unknown after
interruption; it cannot become `retrieved=false` or `invoked=false`. Its separate
[program](native-catalog-metrics-killed-probe.py.txt) preserves the fault setup.

The implicit probe enabled code-mode features in its isolated configuration. It
does not establish which settings were necessary or authorize changing a live
worker. The earlier full-request text search for tool errors matched generic
prompt text and was replaced by actual command status and scoped tool-result
checks. The [historical receipt check](catalog-research-historical-receipts-verified.json)
confirmed 16 pilot receipts and one qualification receipt with observed tool use.
Their frozen results remain unchanged.

OpenAI documents `skill.injected` with skill and status attributes, plus counts
of enabled, retained and truncated skills. Metric names in that catalog omit
the `codex.` prefix. It also documents tool-call metrics. Export is asynchronous;
tool-result logs may contain output snippets. These facts favor a local,
metrics-only investigation rather than unrestricted log collection.
[Official telemetry documentation](https://learn.chatgpt.com/docs/config-file/config-advanced).

Skills use progressive disclosure: the initial list contains names, descriptions
and paths, while full instructions are loaded on selection. Large lists can
omit skills. Installation therefore does not establish exposure for every task.
[Official skills documentation](https://learn.chatgpt.com/docs/build-skills).

## What remains to verify

| Observation | Potential source | Missing proof |
| --- | --- | --- |
| Candidate exposed | Frozen inventory plus enabled/retained/truncated counts | Exact pinned-version rendering behavior and candidate-specific inclusion |
| Instructions loaded | Skill injection metric | Status semantics, implicit-selection coverage, attempt correlation and delivery completeness |
| Candidate invoked | Existing canonical tool events | A skill can guide shell/Python work without a uniquely attributable plugin tool call |
| Candidate not selected | Complete observation interval | Missing events can also mean missing export, unsupported instrumentation or abrupt shutdown |

## Next bounded check

1. Completed the configuration check: Codex 0.154.0 accepted `--strict-config`
   and initialized with an OTLP/HTTP JSON metrics exporter, logs/traces disabled
   and analytics disabled. The disposable worker had no credentials, mounts,
   external network or model calls. It required termination after stdin closed;
   this does not prove graceful exporter flushing. See the
   [raw offline observation](native-catalog-metrics-config-probe.json).
   Negative controls rejected both an
   [unknown configuration key](native-catalog-metrics-unknown-key-probe.json)
   and an [invalid exporter](native-catalog-metrics-invalid-exporter-probe.json)
   before initialization, confirming that these settings were parsed.
2. Review an immutable assessment profile using a local collector, with log
   and trace export disabled. Accept only declared metric names and attributes;
   discard unknown fields without storing raw payloads. Keep the collector
   inaccessible to task commands and any supporting integrations so they cannot
   forge evidence. The offline probe required analytics enabled; authenticating
   the worker and changing its effective telemetry policy needs new conformance.
3. Explicit injection, scripted implicit reading, an ignored skill, EOF delivery,
   rejected export and killed-worker loss now have offline observations. The
   [shutdown fault record](native-catalog-metrics-shutdown-research.json) shows
   why an integration must check collector delivery independently of process
   success. Candidate-specific exposure, truncated catalogs and complete negative
   observations remain unverified. Reserve real model calls on the
   same grant; the local response stub cannot establish learned selection.
4. Map only verified observations into canonical evidence. Keep injection,
   invocation and task correctness separate. Unknown observations remain unknown;
   no report or release flag may turn them into false values.

The existing AEEP telemetry module emits optional coordinator spans; it does not
collect Codex metrics. Reuse the existing adapter and evidence journal if this
path works. A metrics counter alone cannot close the native-catalog release gate.
