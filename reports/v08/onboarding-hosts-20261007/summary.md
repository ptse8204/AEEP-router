# October 7 host and provider verification

The operator authorized GitHub Actions WSL checks and pushing the completed work.
Human testing is deferred to the operator's next prompt. No paid model/provider
request, protected sign-in or release publication was performed.

| Check | Observed result | Evidence and limits |
|---|---|---|
| Real WSL 1 and 2 | Passed installer, managed Python fallback, rerun, operator edit preservation, denial/export, restore, disconnect and uninstall | [Windows workflow](https://github.com/ptse8204/AEEP-router/actions/runs/37592596626), `wsl-final/` retains both actual Microsoft kernels, source revisions, release hashes and results. Earlier runs are retained separately. |
| Claude Code 2.1.292 | Distinct AEEP inventories, denial and restore after host reload, connection removal | `claude-result.json`. Native permission rule creation/restoration was exercised; no model turn tested native permission enforcement. Native denied tools remain in MCP status inventory. |
| DSH installed services | Distinct inventories; real registry call succeeded, then cached declaration failed after revocation; reload/restore passed | `dsh-result.json`, `dsh-probe.mjs`. Actual Cordis 4.0.1, DSH MCP client/tools/system-prompt services. No model turn, complete agent session or whole-agent isolation claim. |
| Claude native plugin setup | Pinned `frontend-design` installed; catalog import, skill inventory, disable/restore and exact source-copy equality passed | `claude-marketplace-result.json` (fresh install after retry guard) and `claude-marketplace-before-retry-guard.json` (native skill disable/restore). Official source commit `d4226d062928f8d9505dbdeadd10217d23361052`; plugin has one skill and no hooks or tools. Skill invocation/output quality unmeasured. |
| HTTPS MCP | Microsoft Learn setup, modern protocol `2026-07-28`, inventory and read-only documentation search passed | `https-result.json`. No authentication needed; installation retains “not admitted.” No general provider-output or billing claim. |
| DeepSeek API application bridge | Actual declarations and dispatch enforce revocation; runnable example exports schemas and rejects missing credentials before a model request | `api-result.json`. Paid model loop and authenticated provider execution unverified. |
| Rebuilt macOS installer | Passed | `mac-installer-final-result.json`; same bounded journey as WSL. |
| Human usability | Pending, deliberately not run | Scripted checks are not first-time human testing. |

Two product repairs came from these checks. Windows release builds now write
`install.sh` as exact LF bytes matching the published checksum. Claude cannot
clone an arbitrary commit through its remote marketplace reference, so AEEP now
registers a clearly named local catalog with only the reviewed plugin. The preview
names this catalog and explains that updates need a new review. The pinned upstream
checkout is preserved. Retry checks the Git checkout and copied files, refuses operator edits, and rejects redirected snapshot paths before copying.

The first two WSL failures, the initial Claude commit-reference failure, and local
probe architecture/assertion failures remain alongside the successful results.
Claude/Node are Intel binaries under Rosetta; AEEP's managed ARM Python works
across that process boundary. Using the developer's universal Python with ARM-only
extensions did not. This is separate from a native Intel hardware check.

Build resources for the final Windows workflow use the selected D: filesystem,
which had over 140 GiB free. The runner's preinstalled C: filesystem was below
50 GiB; no cleanup was performed there. Earlier workflow builds installed their
build dependencies on C:, a test-storage limitation repaired in the final workflow.

Compile, schemas, lint, typing, policy, compatibility and 13 DSH JavaScript tests
passed. The plain suite passed 1,287 tests with 21 skipped in 562.53 seconds; the
branch-instrumented suite passed the same 1,287 tests with 21 skipped in 850.65
seconds. Combined statement/branch coverage is 81.32%; both required branch gates
passed. The two portable lifecycle fixture cases also passed after their path-only
change. Production source remained unchanged through both full runs. Final WSL
artifacts passed on commit `34bb25e`; the fixture-only successor's WSL run also
[passed](https://github.com/ptse8204/AEEP-router/actions/runs/37593981583).
The first assessment CI job passed 59 cases, skipped six, and failed two lifecycle cases because their fixture hard-coded `/usr/local/bin/docker`. The fixture now uses the current Python executable without launching it; both cases passed locally. The full assessment-boundary job then passed in [Actions](https://github.com/ptse8204/AEEP-router/actions/runs/37593981753); its final log is retained.

Native Windows CI reports POSIX-only type errors (`ci-windows-first-failure.log`);
that job does not establish WSL failure or native Windows support. At the recorded status, Linux/macOS matrix jobs are still running. Superseded CI
runs were cancelled after recording their status. No acceptance threshold changed.

All probe resources are task-owned and retained under
`/tmp/aeep-host-checks-20261007`. `resources.json` records package versions,
integrity and the native binary digest. Prepared candidate assets are under
`dist/v0.8.2-host-checks-final`; publication and the public curl command remain separate.
