# Onboarding implementation validation — October 6, 2026

The implementation is present in the working tree, with locally built 0.8.2
release candidates. It adds guided setup and menus, named agent connections,
connection-bound dispatch controls, searchable catalogs, immutable sourced stack
recommendations, reviewed component setup and reversible native deny rules.
No release was published and the operator's active agent configuration was not
changed. No model call, paid provider call, protected sign-in, assessment campaign
or Docker operation was started by the onboarding work. The assessment fixtures
below are software tests, not new live comparisons or qualification evidence.

## Final software checks

| Check | Result | Record |
|---|---|---|
| Compile `src`, `examples`, `tests` | Passed | [compile](compile.log) |
| Generated schemas `--check` | Passed | [schemas](schemas.log) |
| Ruff | Passed | [lint](ruff.log) |
| Mypy | Passed, 154 source files | [types](mypy.log) |
| Assessment policy | Passed | [policy](policy-check.log) |
| Full pytest | **1,282 passed, 21 skipped** | [plain run](pytest-final-v2.log) |
| Full branch-coverage pytest | **1,282 passed, 21 skipped** | [coverage run](coverage-tests.log) |
| Coverage report | **81.25%**, above the unchanged 80% floor | [report](coverage-report.log), [JSON](coverage.json) |
| Critical branch gates | Passed | [critical coverage](critical-coverage.log) |
| Assessment branch gates | Passed | [assessment coverage](assessment-coverage.log) |
| DSH JavaScript tests | 13 passed | [DSH](dsh-tests-final.log) |
| Strict router compatibility | 56 passed, 1 skipped, 1 disabled | [router check](router-complete.json) |
| Existing economic, DSH safety/comparison/plan, job and provider contracts | Passed | `*-check.log` in this directory |
| Release wheel, pinned requirements, bundle and installer | Built | [build](build-final.log), [asset hashes](release-candidate.json) |

The existing router verifier's `release_ready` field describes its legacy
compatibility checks. It does not close the new live onboarding, platform,
human-usability or publication gates. The warning in both full Python runs is a
pre-existing FastAPI/Starlette TestClient deprecation.

[Source hashes](source-files.json) remained unchanged across the final runs.
The [exact test review](test-review.json) and [active lock amendment](verification-lock-review.json)
record the standing authority. No historical verification lock, qualification
threshold, campaign budget or held-out result was rewritten.

## Actual local journeys

- [Final installer journey](installer-final-result.json): macOS arm64, isolated
  home/project, managed Python 3.12.11 fallback, install, rerun, preserved operator
  edit, deny/export/restore, disconnect and uninstall. The driver is
  `scripts/check_installer.py`; [stdout](installer-final.log) is retained.
- [Actual candidate upgrade](upgrade-result.json): switched the earlier isolated
  runtime to the final candidate, retained a rollback pointer and preserved the
  manifest, catalog settings, access filters and all 45 prior immutable records.
  This used local built assets, not an unpublished GitHub download.
- [Installed MCP process](stdio-probe.json): modern protocol initialization,
  filtered inventory and revocation while the process runs; an old declaration
  cannot call the revoked tool. This does not test native host reload behavior.
- [Packaged DeepSeek example](api-example.json): offline declarations, no model
  request or API key access, and no configuration environment override required.
- [Live catalog search](discovery-live.json): 26 candidates, including successful
  Anthropic results while some MCP queries timed out. Errors and truncation remain
  in the source records.
- [Packaged video comparison](video-check.md): seven named stages from default
  catalog searches plus sourced host web findings. It reports **setup required**,
  with unknown prices and measured quality. No video was generated.

## Retained failures and limits

The initial full run overlapped implementation edits and failed 20 checks.
Those results remain in [the initial log](pytest-initial.log). Four source-bound
assessment checks then passed together on unchanged source in
[the focused recheck](assessment-recheck.log). The next full plain run had one
failure from the old inventory-fixture digest; the exact lock amendment and
[subsequent repairs](final-repairs-v2.log) resolved it. Both final full runs passed.
The initial stdio probe expected the wrong denial envelope, then reused its own
retained deny rule; [both probe errors](stdio-probe-initial.json) remain recorded.
The final probe explicitly sets up its allow rule before testing revocation.

Still unverified or outside this release:

- Real Linux/WSL and x86_64 installation. The no-publication workflow in
  `.github/workflows/installer.yml` is prepared but was not dispatched here.
- Native Codex/Claude/DSH tool exposure after reload, third-party package
  installation, provider authentication and metered billing readiness.
- First-time human completion and comprehension of the README/CLI journey.
- Whole-agent isolation and unmanaged alternative tool connections.
- Native command-based catalog sources, plugins outside the pinned checkout and
  unresolved native plugin dependencies require a separate handoff. API component
  descriptors require application wiring and normal intake/admission.

The public latest-release curl command remains withheld until publication and
platform acceptance. Final local assets are in `dist/v0.8.2-onboarding-final`.
The [resource record](release-candidate.json) lists exact hashes and retained task
paths. Runtimes, grants, receipts and recovery data were preserved; no blanket
cleanup was performed, and the host stayed above its 50 GiB reserve.
