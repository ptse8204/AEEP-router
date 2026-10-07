# Documentation refresh — October 7, 2026

The operator approved the documentation implementation plan in this chat.
This change updates active guides and examples, adds a reader-oriented index,
puts agent connection first in the README, and records reusable writing rules
in AGENTS.md and CONTRIBUTING.md. Runtime code, schemas, package versions,
assessment definitions and CI workflows are outside this change.

## Audit and corrections

| Finding | Correction and source |
|---|---|
| Quick start followed detailed benchmark tables | README now leads through source installation, setup, review, restart and public catalog search; detailed measurements remain in docs/EVIDENCE.md and original reports. |
| Setup assumed an installed checkout and mixed source/installer launchers | docs/ONBOARDING.md gives source prerequisites and explains the saved interpreter path. `src/aeep/onboarding.py:connect` binds `sys.executable`; the fixed marketplace launcher separately requires its dedicated runtime. |
| Integration introduction described ten tools as the entire interface | It now identifies the ten legacy routing/economic tools and explains profile, discovery and connection filtering; verified against `AEEPToolService.list_tools` and `PLANNING_TOOLS`. |
| Demo and marketplace README linked to removed installation instructions | They now link to setup and dedicated-runtime prerequisites. Demo reproduction distinguishes the recorded installer environment from a source environment. |
| Subscription guide advertised an unverified package-index installation | It now uses the verified source-install path. No package publication is inferred. |
| Software evidence called an October 4 source current | Dated results remain tied to their revisions; the guide links later completed local checks without turning pending runner work into a release claim. |
| Agent integration linked a skill directory without an index | Link now targets the existing SKILL.md; packaged skill bytes remain unchanged. |
| Long references and many examples lacked an entry point | Added topic navigation, specific prerequisites/results and index links; old section headings and referenced README anchors remain available. |
| Fixture walkthroughs presented regeneration before retained-result checks | Verification now comes first; regeneration is a separate section that uses a separate checkout. Existing commands are retained, and the safe check variants pass. |
| No local Markdown/link checks | Makefile targets use markdownlint-cli2 0.23.3 and Lychee 0.24.2 with the same 47-file scope. Link checking is offline and validates local fragments. CI remains unchanged. |

Older accounting, package, trust and migration versions retain their contract
meanings. Adopted ADRs, reports, roadmap/status history, changelog, assessment
policy and packaged skills are excluded from editorial rewriting. The existing
uncommitted Windows summary and plan-coverage edits are preserved.

## Validation

The initial local checks found four existing extra blank lines and a link to a
skill directory without an index; both classes were corrected.

| Check | Result |
|---|---|
| Local documentation checks | 47 files; Markdown lint passes. Offline Lychee: 493 occurrences, 336 unique links, 463 OK, 30 external exclusions, zero errors. The exact-version guard rejects a mismatched Lychee binary. |
| Version consistency | Two existing tests pass. |
| Compile, generated schemas, Ruff, mypy and assessment policy | Pass. |
| Existing CI proof checks | Economic gates, DSH campaign/retained live records/native plan, job sandbox and provider-package verification pass. No live campaign was run. |
| Strict legacy router compatibility | All required profiles pass; live OpenAI proof remains skipped and live marketplace networking disabled. The verifier API saved a new task record rather than overwriting historical CLI report paths. |
| Wheel and sdist | Build passes; wheel contains the current documentation index and fingerprinted integration READMEs. Artifacts remain local and unpublished. |
| Ordinary pytest | Final frozen source: 1,293 passed, 21 skipped, one existing Starlette deprecation warning; 647.55 seconds. Source digest was unchanged across this fresh full run. |
| Branch coverage | Post-commit source: 1,293 passed, 21 skipped, one existing warning; 991.36 seconds. Combined coverage 81.32027485275745% (statements 84.84657419083649%, branches 71.12345893384268%); the 80% floor and both required critical/assessment branch gates pass. |
| Node integration tests | 12 passed. |
| Isolated command examples | Quickstart and loopback HTTP return 7 characters, 2 words, 1 line; stdio MCP returns 13 characters, 3 words, 1 line. Each execution has a valid receipt. |
| Navigation and preservation audit | Every active guide/example/reference is linked from the index. Existing heading anchors, all original code lines outside README, and all nonblank architecture/specification/security text remain. 123 original code blocks remain exact; two campaign blocks were split to put checking first. |
| Rendered review | Reviewed the README, its setup shortcut, demo GIF, index tables and expanded specification navigation in a temporary local preview. This is an agent review, not human-usability evidence. |

The temporary MCP manifest initially failed because relocating it changed its
relative server directory and the shell lacked the activated environment's
`python` command. The corrected fixture binds the original example directory
and provides that interpreter on its private PATH; no repository command or
runtime change was needed. Quickstart/HTTP databases, MCP transport and all
synthetic outputs stayed inside task-owned temporary storage.

All 25 external URLs (30 occurrences) have a separate
[manual review record](external-links-review.json). Official pages and redirects
were retrieved, and the demo's GitHub blob page and local media were confirmed.
The exact DeepSeek Tool Calls URL and content appear in its official search
index, but direct retrieval timed out twice; live reachability remains unverified.
No URL was changed based on a timeout. Authoring references were checked against
[Diátaxis](https://diataxis.fr/), the official
[markdownlint-cli2 release](https://github.com/DavidAnson/markdownlint-cli2/releases/tag/v0.23.3)
and the official [Lychee release](https://github.com/lycheeverse/lychee/releases/tag/lychee-v0.24.2).
The offline target does not assert that every external URL is reachable.

During verification, another workspace task committed Windows CI work as
`47f20ee6d84814980717df68886cc3971ce7df25`: CI diagnostics, the worker-lifecycle
test harness, and its existing records changed. That commit also retained this
task's provisional plan-coverage entry. Those changes are preserved and are not
part of the documentation implementation. The coverage run started after the
fixture edit. A fresh ordinary invocation of that exact test, plus compile,
Ruff, version and policy checks, verifies the updated fixture separately. Its
standing-authority review remains in the Windows record. Both completed final
full runs use the post-commit source. The earlier ordinary run also passed
1,293 tests with 21 skipped (682.13 seconds), but began before the concurrent
edit and is not claimed as a frozen-source run of the final tree. Its original
source-drift observation remains in [checks.json](checks.json), alongside the
fresh result; [validation.log](validation.log) retains the check output.

The default `/usr/bin/make` requested Xcode license acceptance. Validation uses
the existing `/Library/Developer/CommandLineTools/usr/bin/make`, without accepting
licenses or changing the global developer directory. Contributors may use any
working GNU Make installation.

## Evidence and resources

Integration READMEs contribute to `verification_source_digest`. Their edits
change the current source binding; historical live qualifications and conformance
remain evidence for their original revisions. Fresh applicable evidence is still
required before applying them to this revision. No historical verification lock,
campaign result, qualification threshold, budget or credential state is changed.
The original three-way comparison remains unrun, failed qualifications stay
negative, and human comprehension remains unmeasured.

The documentation edits change the verification source digest from
`1cd695b8eaf41a6a081b9fa3c1f675e158fa6573e4ad70b05139142fbc8d1ef9` to
`28274fd6773951926d6dd34a45c6659c88a02271e5aaba835f595674f495c525`.
The concurrent test-fixture change then produces source
`05aa06e6d8f35f8c0e2d5dd7275e54f29f2348a99b97e96fd9ecca6f98be9a37`.
Runtime code, schemas and package versions retain their starting bytes. The
initial preservation audit matched 4,638 historical/policy/skill/CI files;
subsequent changes are limited to the other task's named CI/fixture/record work.
The entire pre-existing plan-coverage body remains after this task's new entry.

The host filesystem had 72 GiB available before authoring-tool setup, above the
50 GiB reserve. No Docker resource was created or removed. Authoring resources
are retained in the task-owned temporary directory
`/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/aeep-docs-refresh-20261007-v3gcsw1_`:
the initial tracked-file hash inventory, copies of the two pre-existing dirty
records, pinned Lychee release metadata/archive/binary, check logs and previews.
The Lychee arm64 macOS archive SHA-256 is
`c9d3740ea2d891854d37116c9fba840f37b6e7c89d330e7db84ac333631c4977`,
verified against the official release asset digest. npm's existing cache holds
markdownlint-cli2 0.23.3 and its dependencies; no Python dependency was added.
Final package filenames, sizes and SHA-256 hashes are in `checks.json`. The
temporary preview server and browser tab were closed. No task-owned service
remains running.

No production host configuration, publication, sign-in, model trial or paid
provider execution is part of this refresh. Documentation review supplies no
human-usability or live-release evidence.
