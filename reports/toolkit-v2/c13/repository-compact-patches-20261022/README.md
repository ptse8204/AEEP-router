# Compact repository patch transport

A real three-file SQL repair produced774091 bytes of replacement-file JSON,
exceeding the old patch bound. Version3 cases now use an explicit gzip-JSON output
field. That reference becomes147888 compressed bytes and fits existing artifact
transport. Source/archive/member/payload limits stay unchanged. Standard-library
gzip is already used for source archives; no parser, executable or dependency
was added. These artifact sizes do not establish token,time,memory or cash savings.

Legacy v1/v2 case records,truth schemas,recipe IDs/digests and observer bytes compare
identically before and after the change. Their encodings and limits remain.
V3 explicitly selects the new format; invalid/corrupt/truncated/oversized streams,
duplicate JSON keys and unsafe/source-out-of-scope edits fail before execution.
The decoded patch is capped at the existing4000000-byte source-tree bound.

All13 configured source commands passed on unchanged source59b9d61c. Both full
runs passed1676 tests with21 skips and the existing Starlette warning. Total
coverage is82%; both branch gates,Ruff,layering,mypy and wheel/source builds pass.
Fifty-three focused tests pass. Offline docs lint passed69 files. No broad rerun
is needed on unchanged source. Initial assertion/import-format issues were fixed
before the full run; their record remains. A nested installed-fixture escape was
caught and corrected by compilation before review or execution.

The extra offline CI proof initially found11 stale index bindings to one unchanged
C07 test file. All executable checks passed. One current index entry was refreshed;
the old lock and failed report remain here. The current offline proof passes.
It supplies no live qualification or release authority. The optional DSH runtime
check cannot import @deepseek-ai/dsh-llm;12 independent Node tests pass. Its missing
runtime dependency remains a separate unresolved check; no npm installation ran.

Five v3 cases and19 inert variants are prepared: four SQL issue repairs from
distinct revisions plus Circuitbreaker with explicit existing mocker/asyncio
plugins. All assertions are retained. The first three-case draft remains. Current
source-bound runtime conformance is not inherited: reviewae4ab2f0 requires three
fresh boundary/state/runtime probes before subject execution. At most22 offline
calls,24 existing-grant operations and920 reserved seconds on the existing image;
no models,downloads,image changes,installations or retained-resource cleanup.
Preparation verified62 assets,22 classifier fixtures and25 first-party grader
guards. Actual external execution still requires exact approval.

The preceding pool has15 provisional cases on sourcef694024c,including the separately
recorded Beniget Python3.13 adaptation. Neither that pool nor these static cases
freeze full8/28/105 stages. Required-use qualification,optional-use value,
independent selection,human controls,workload-derived resource acceptance and
release remain open. The next review combines this contained check with the
changed wheel and pinned offline docs checker; no architecture decision is needed.
