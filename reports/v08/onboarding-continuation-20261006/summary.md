# Continued onboarding verification — October 6, 2026

Live Codex verification found a restoration bug: removing an adopted deny rule
left an empty `disabled_tools` field, so disconnect rejected AEEP's own entry as
modified. The fix remembers whether AEEP introduced that field and removes it
when the last adopted rule is restored, in either order. Operator-removed rules
and fields stay unchanged. Four added regression cases cover those paths.

## Actual checks

| Check | Result | Evidence |
|---|---|---|
| Linux arm64, starting without Python | Passed in a container using an existing image; install, rerun, user edit preservation, deny/export/restore, disconnect and uninstall | [Final result](linux-final-result.json) |
| Linux x86_64 under emulation | Passed the same no-Python and installer lifecycle journey with an already-cached Ubuntu image | [x86 Linux result](linux-x86-result.json) |
| macOS arm64 packaged installer | Passed the same journey after the fix | [Installer log](installer-mac.log) |
| macOS x86_64 under Rosetta | Passed install and the same lifecycle journey; physical Intel hardware not tested | [x86 result](macos-x86-result.json) |
| Recovery after setup failure | Passed corrected-project rerun with the same active runtime and preserved manifest edit | [Recovery result](recovery-result.json) |
| Installed Codex CLI 0.154.0 | Passed separate connection inventories, a real MCP call, stale-declaration revocation, native `disabled_tools` after reload, restoration and disconnect | [Codex result](codex-result.json) |
| Python time and npm memory reference packages | Reviewed pinned installation and repeat apply passed; owned API descriptors and read-only MCP checks passed using explicit legacy protocol mode | [Component result](components-result.json) |
| Native Codex marketplace setup | Passed pinned public AEEP 0.8.1 install, recorded-failure retry and repeated apply in an isolated Codex home; does not publish the new candidate | [Native result](native-marketplace-result.json) |
| Existing marketplace import | Setup offered the real Codex inventory entry, imported its location and returned the plugin through metadata search | [Import result](catalog-import-result.json) |
| Actual terminal setup/menu | Passed setup, local catalog addition, deny, explain, restore and setup check | [Menu result](menu-result.json) |

The Codex check used an empty host home without a model turn or sign-in. The
package checks ran `get_current_time` for UTC and `read_graph` against an empty
isolated store. Neither package was admitted to AEEP routing. No paid call,
assessment campaign, production host edit or publication occurred.

The time reference server did not pass AEEP's automatic modern-protocol probe.
The retained [failure](components-auto-protocol.log) led to an explicit legacy
check, not a weaker protocol guard. Generated API descriptors still require the
application to choose a compatible client and complete normal intake/admission.

The initial Codex probe expected an MCP error envelope; the actual host returned
a protocol unknown-tool error. Its [initial result](codex-result-initial.json)
is retained. The corrected probe then found the real restoration bug; that
[pre-fix failure](codex-result-pre-fix.json) is also retained. The final probe
passes on the rebuilt candidate. Early regression assertions expected deletion
of an empty config file; they were corrected to the existing empty-file behavior.

Native installation initially failed because the probe supplied a nonexistent
`CODEX_HOME`. The [diagnostic](native-marketplace-diagnostic.log) is retained.
Creating the isolated test directory and explicitly retrying the recorded failed
setup passed, without changing product code.

## Final software checks

| Check | Result | Evidence |
|---|---|---|
| Compile, generated schemas, assessment policy | Passed | [Driver results](checks.json), [explicit source-path schema check](schemas-explicit-path.log) |
| Whole-repository Ruff and Mypy | Passed; 154 source files type-checked | [Lint](ruff-all.log), [types](mypy.log) |
| Full plain pytest | **1,286 passed, 21 skipped** | [Plain run](pytest.log) |
| Full branch-coverage pytest | **1,286 passed, 21 skipped** | [Covered run](coverage-tests.log) |
| Overall coverage | **81.26%**, above the unchanged 80% floor | [Coverage report](coverage-report.log) |
| Critical and assessment branch thresholds | Both passed against this run's coverage JSON | [Final gate commands](coverage-gates-final.json) |
| DSH JavaScript tests | 13 passed | [DSH](dsh-tests-all.log) |
| Strict router and existing policy/compatibility checks | Passed within their existing scopes | [Router](router-complete.json), [other checks](compatibility-checks.json) |
| Source integrity | Unchanged across both final test runs | [Source check](source-check.json) |

The only warning in both full Python runs is the existing Starlette TestClient
deprecation. The first final-threshold invocation omitted its coverage-file
argument: the critical checker used its historical default, and the assessment
checker rejected the invocation. Those outputs remain in the original driver
record. Both checkers were then run successfully against the new coverage JSON;
only the explicit-path final results above count as current threshold evidence.
The router verifier's legacy `release_ready` flag does not close onboarding or
publication gates.

## Remaining gates

WSL, physical x86 hardware, live Claude/DSH reload behavior,
native Claude marketplace installation, HTTPS provider authentication and paid-provider
readiness remain unverified. The [human exercise](human-usability.md) is pending;
a scripted terminal run is not a comprehension test. Public release publication
remains a separate action, so the README does not advertise an unavailable
latest-release installer. Assets in `dist/v0.8.2-onboarding-continuation`
remain a local candidate built from the recorded dirty working tree. A clean
tagged build and verification of the public download URL remain release gates.

The three stopped Linux containers and all isolated task directories are retained.
The [resource record](resources.json) records their IDs, the reused image, asset
hashes and free space. No Docker images were built or pulled, and no volume or
unknown resource was removed. The final resource check recorded 103.15 GiB free, above the 50 GiB reserve.

Definitions and changes are recorded under the standing finite-test authority in
[the review](review.json). Both final test runs and required branch thresholds passed. Historical records
are unchanged.
