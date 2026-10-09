# C04/C05 acceptance audit

The implementation gates can be evaluated separately from live candidate value.
Source `5386064` passed the full software checks. The additive sharing/catalog source `f3b7f50` subsequently passed both
1,532-test suites, both branch gates and the required proof/build/quality checks.
Its fresh Router-disabled six-worker replay and two zero-turn native probes
also passed with cleanup. This audit does not confer authenticated host or release qualification.

## C04: real harness and controlled adapter

| Required behavior | Evidence | Limit |
| --- | --- | --- |
| Prefer upstream; record fallback choice | D13/D19/D40 and `c04/codex-harness-contract` records | ASE 0.7.0 has verified execution only for the recorded scripted path; its native token/launch contract failed review |
| Real external engine and separate arms | `c06/verified-journey/checks.json`, six verified receipts; `c06/verified-router-free` repeats without Router construction | Deterministic fixtures, not model choice or live efficacy |
| Exact source, candidate and shared inputs | `integrations/toolkit/test_definition.py`, `test_worker_payload.py`, `test_evaluate.py`; reviewed plan hashes | Modified source or candidate invalidates review |
| Independent worker files and normal shared tools | `c04/native-current/integrated-result.json` | Bounded zero-turn probes; no authenticated conformance |
| Failure, timeout and unresolved operation behavior | `integrations/toolkit/test_partial.py`; retained failure/interruption evidence in `c06/verified-journey` | Missing trials remain missing; no blind retries |
| Existing managed fallback and accounting | `tests/test_toolkit_managed.py`, `test_toolkit_prompt_binding.py`, missing-token correction evidence | Missing identity, prompt, conformance or usage remains a gap |
| Explicit backend selection | `tests/test_toolkit_eval_cli.py` | No automatic switch after failure; checkout assets still required for execution |

The limited engineering scope meets C04's software exit checks. Full host
conformance and live optional-access comparisons remain C07 requirements.

## C05: comparison and reports

| Required behavior | Executed regression evidence |
| --- | --- |
| Fewer tokens with worse success; missing grading | `test_toolkit_reporting.py` |
| Cached/reasoning overlap and missing telemetry | `test_toolkit_contracts.py`, `test_toolkit_reporting.py` |
| Zero successes, unknown cash, failed-run costs, recurring fees | `test_toolkit_cash.py` |
| Missing exposure/results, mismatched host/model/source cohorts | `test_toolkit_reporting.py`, `test_toolkit_managed.py` |
| Long tails, means, medians, zero denominator, finite output | `test_toolkit_means.py`, `test_toolkit_reporting.py` |
| Existing intervals, guardrails, operation costs and canonical outcome | `test_toolkit_managed_analysis.py`; reproducible order probe and branch gates |
| Readable static HTML/Markdown with task-family scope | `c06/verified-journey/result/report.html`, `report.md` |

Descriptive reports remain NOT_ASSESSED. The separate canonical report preserves
its existing adjudication and conservative missing-cost semantics. Synthetic
records cannot establish benefit. Developer metadata is an assertion until
verified; no actual ownership or support destination was authenticated.

## Remaining critical-path gate

C06 still needs the exact private package installation/removal test and its
installed-CLI results. The proposed 33-wheel review remains pending. Full managed
execution requires checkout assets and applicable native conformance; a successful
installed metadata/report command would not prove live evaluation readiness.
