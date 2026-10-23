# Provisional repository workloads

These cases prepare AEEP to compare capabilities on real source changes and on
audits where correct behavior means leaving working code alone. They reuse
published issue contracts, tests and repairs through the existing AEEP grader.
Actual approval `4cfc412d` completed fourteen calls. Six cases reproduced, two references failed and their negative calls were skipped. No case has been admitted or frozen into a complete assessment cohort.

| Repository | Bounded task | Type |
|---|---|---|
| Python-markdownify | Preserve required newlines around definition lists | Single-file repair |
| Python-Markdown | Handle malformed HTML-comment input without looping | Single-file repair |
| Mahjong | Audit a corrected shanten calculation and preserve correct source | Authored audit |
| Dissect.cstruct | Repair equality/hash behavior across enum and structure types | Multi-file repair |
| Mockito-python | Add the requested no-op answer method | Multi-file repair |
| Files-to-prompt | Audit corrected stdin file-list handling and preserve correct source | Authored audit |
| Freezegun | Handle a parametrized argument named `func` | Single-file repair |
| Jsonpickle | Honor excluded fields when serializing slotted objects | Single-file repair |

Exact revisions, licenses, source hashes and omitted non-source edits are in
`prepared-cases.json`. Both audits start from the published corrected source;
their origin is explicitly authored. An extra protected test checks that editable
source bytes stay unchanged. They are not relabeled upstream repair issues.

Static preparation verified sixteen payloads, 68 assets and 368 required test
identities. The classifier passed twelve checks, including missing, skipped,
errored and unexpectedly passing negative observations. No source from these
repositories or their wheels was executed during preparation. Declared upstream
Python versions are adapted to 3.13 with pytest 8.3.5 and exact pure wheels loaded
inside the existing offline container. Missing dependencies or incompatible
tests may make a case ineligible; this review does not authorize installing a fix.

`operation-review.json` permits one finite batch after specific approval: at most
sixteen calls, eighteen existing-grant operations and 710 reserved seconds. Each
reference must pass every required test; its counterexample must have the frozen
expected failures and preservation passes. A failed reference skips that case's
negative call. Independent cases continue after verified canonical completion and
cleanup. Common source, authority, accounting or lifecycle uncertainty stops all
dispatch. Raw bounded public-test replies are saved before protocol validation.
No model, installer, download, image change, docs rerun, credential, cash,
activation, release or historical replay is included.

These eight candidates do not yet constitute the formal eight-case screening
stage. Their provisional family counts are 4/2/2, while final stage assignments
must satisfy the existing balance and independence rules. Full 8/28/105 cohorts,
required-use model qualification, optional-use value comparisons and independent
selection outcomes remain open. Reference reproduction does not demonstrate
capability usefulness. Resource acceptance is a separate workload-derived check.

`cohort-capacity.json` records the wider metadata pool: 435 candidates across 243
repositories, including 184 repositories with single-file repairs and 101 with
multi-file repairs. Those counts satisfy necessary pool-size checks only. The
source licenses, runtime reproduction and joint independent stage assignment
remain unverified. No extra case was adopted by this read-only audit.

The completion audit reopens all fourteen completed attempts/receipts and confirms
owned-container cleanup. Sixteen operations charged 24.288069125264883 seconds;
model/cash counters did not change. `exclusion-analysis.json` records the Click
API incompatibility and missing required Ruff identities. The original frozen
expectations remain intact. Earlier preparation-only statements describe what
was known before execution; `completion-audit.json` is the terminal outcome.
