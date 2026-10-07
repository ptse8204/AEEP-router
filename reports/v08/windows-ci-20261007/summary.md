# Windows CI repair — October 7, 2026

Current source under verification: `41531fc93c0f2db49f43b0bc20f4b8075375ed52`.
The earlier phase results below apply to their linked revisions.

- POSIX-only file and process operations reject missing primitives before effects.
  Artifact reads retain the portable fallback; symlink protections remain enabled
  wherever the platform supplies them.
- Native-policy fixtures use the runner-owned temporary directory, outside the
  forbidden `/tmp` and `/var/tmp` roots. A construction-only managed-worker fixture
  uses the actual Python executable instead of a hard-coded Docker path.
- The assessment policy checker reads UTF-8 explicitly on Windows.
- Ordinary local pytest: 1,291 passed, 21 skipped, one existing warning, 553.95 seconds.
- Focused guards and Codex invocation: 29 passed. Artifact/guard checks: seven passed.
- Compile, schema freshness, Ruff, native-platform mypy, Windows-target mypy, and
  assessment policy checks pass locally.
- Branch-coverage pytest: 1,291 passed, 21 skipped, one existing warning, 853.47
  seconds. Combined coverage is 81.32768046413031%; both required critical and
  assessment branch-coverage gates pass.
- GitHub Actions has passed Windows pre-test gates, DSH tests, and real container
  boundary checks (61 passed, six skipped). Linux Python 3.12 and 3.13 have passed
  the full job including strict verification and package build. Windows pytest
  and the remaining OS jobs are pending.

[Current CI run](https://github.com/ptse8204/AEEP-router/actions/runs/37670631551).
The earlier workflow-context error and Windows UTF-8 failure are retained in
[the first run](https://github.com/ptse8204/AEEP-router/actions/runs/37670258261) and
[the second run](https://github.com/ptse8204/AEEP-router/actions/runs/37670349862).

The test-definition review uses the standing delegation in
`docs/ASSESSMENT_TESTING.md`; it changes no assessment thresholds, historical
evidence, payment authority, or release authority. Human testing remains deferred
to the operator. These checks do not establish authenticated provider/model usage.

## Follow-up fixture review

The macOS job reproduced relay startup timeouts. The relay test now imports the
standalone stdlib module in the same way as `worker-launch`, preserving the
10-second test deadline. Its process-group integration cases are POSIX-only;
`test_posix_guards.py` checks rejection on unsupported hosts.

The synthetic assessment baseline now uses the same synchronous thread-pool
dispatch path as its candidate, with an explicit 20 ms delay. This removes the
async-versus-thread dispatch difference from the fixture. Qualification counts,
comparison thresholds, and production campaign definitions remain unchanged.
These fixture results cannot establish measured plugin benefit. Exact reviewed
definitions:

- `tests/test_posix_guards.py`: `7f22636d394a6946e462fa55f46a2ffb1d81632277da32c8cdfc7ff35359d43e`
- `tests/test_v08_codex_invocation.py`: `8fb53593b3ca02a0eb91229a2d468541b68002f5600b4de4e6b5e5178864c2e8`
- `tests/test_v08_assessment.py`: `68b6496df2b7c8305c03d92d31e8f6e18b81916e93cab6fc18c4da856aeb1e41`

## Native Windows full-run findings and second repair

The first complete native Windows run ended with 1,077 passed, 162 failed,
59 skipped, and 14 errors (2,215 seconds). The Windows pre-test gates passed.
Most failures rejected Linux container paths using the coordinator's Windows
path rules. Worker executable and differential paths now use POSIX semantics;
local executables still require a host-absolute path. Reviewed worker skill
paths and generated configuration retain their worker path syntax. Bundled
workbook and SkillsBench Python sources are decoded as UTF-8.

The remaining changes correct local test fixture paths, LF-preserving fixtures,
Windows executable suffix handling, and platform-specific assertions. Only
POSIX native task activation and process-group/tree-transfer integration cases
are skipped on native Windows; their portable authority tests remain enabled,
and unsupported primitives have explicit rejection tests. macOS/Linux keep the
full applicable suite. A Windows portability smoke runs before the full suite.

The worker-exit test now waits at most 180 seconds for its full synthetic
assessment and cleans up the child if that wait fails. This is a harness deadline,
not a worker execution allowance. Invalid terminal events in the fake App Server
are delivered in one burst so their receipt precedes the assertion; production
protocol handling is unchanged. Fresh focused relay/assessment tests (37) and
subscription-adapter tests (14) pass locally, as does the worker-exit test.
The second repair remains pending native Windows CI and fresh full coverage.

Additional exact reviewed definitions:

- `tests/test_posix_guards.py`: `73d71d4a03c537e8d7233443078fc620740e680f1b433d96035d66c24cb02b2c`
- `tests/test_v08_assessment_interfaces.py`: `ec2cc58a4b83bd0e37fef8c7a82175323118f861c25cf43ce852dc877934dfeb`
- `tests/fixtures/fake_codex_app_server.py`: `620b757fc63bccbdfdbd5f1c666e225058e69a36132ae51b71fff4c245998cde`

## Windows smoke follow-up

Run 37676416239 narrowed the smoke failures to seven (127 passed, seven skipped).
Runtime executable paths are now validated on the coordinator platform; worker
binaries and Unix socket paths retain POSIX semantics. The shared fixture uses
the current Python executable for its non-launching runtime. Local executable
fixtures, exact LF canaries, and search input fixtures were corrected. The trusted
SkillsBench software test writes its identical contained source to a temporary
UTF-8 file, avoiding Windows' command-line limit without changing the recipe or
its container execution contract. Native Windows still needs another smoke run.

## Full local verification and remaining runner check

On frozen revision `074a60eccf565ee2653e838a24ccffaa0f005fe3`, ordinary pytest
passed 1,293 tests with 21 skipped (607.18 seconds). Branch coverage passed the
same tests (928.27 seconds); critical and assessment coverage gates pass. The
`final-*` files in this directory retain that revision's results. Compile, schema,
Ruff, native and Windows-target typing, and policy checks also passed.

[Run 37677142838](https://github.com/ptse8204/AEEP-router/actions/runs/37677142838)
passed the native Windows portability smoke, DSH, and real container boundaries
(61 passed, six skipped). Its macOS suite passed 1,273 tests with 37 skipped but
still timed out in four relay cases. The diagnostic run
[37680861506](https://github.com/ptse8204/AEEP-router/actions/runs/37680861506)
placed the stall in HTTP server initialization. The loopback collector now binds
without HTTPServer's unnecessary reverse-DNS lookup. The relay tests reject any
attempt to resolve the server name, retain their 10-second deadline, and emit a
stack trace on a stall. All 31 focused relay/primitive checks pass locally.

The diagnostic run was canceled after its completed macOS failure was retrieved.
[Run 37681197389](https://github.com/ptse8204/AEEP-router/actions/runs/37681197389)
checks the follow-up. Native Windows setup remains outside the supported
macOS/Linux/WSL onboarding scope; unsupported protected operations fail closed.
No security policy, campaign threshold, or provider admission was relaxed.

The follow-up macOS early relay gate passed on Actions. Exact follow-up review
under the standing delegation (software regression checks, not campaign evidence):

- `src/aeep/hosts/codex_metrics.py`: `d551e2f4e70ce875df945b1b3ec7e582463a53508753844ef1b34b45228c90e1`
- `tests/test_v08_codex_invocation.py`: `fe66e8d00c08fb777a340cab9adfff9d73d78613394e9493e2b698cd57115070`
- `tests/test_v08_skillsbench_recipe.py`: `9f7a192a507a584f9543c8292501166ee50d702ab1ded4dc1ffeefad0fcf66fb`
- `tests/test_v08_managed_workers.py`: `767d4866dac1dab77fe125e09962996f03850fb7ee5b450e24d35872498baa4d`
- `tests/test_posix_guards.py`: `ef7117c136e5b44b2e88ce69aaf5e614a453dd25285e02e977b7cebd9d296c66`

Linux 3.11 and 3.12 each passed 1,276 tests with 37 skipped and failed only the
new Windows-path simulation: `ntpath.isabs('/opt/...')` differs before Python
3.13. The simulation now uses `PureWindowsPath.is_absolute` consistently across
Python versions; six focused guards pass. Production validation is unchanged.
Linux 3.13 passed 1,277 tests, 37 skipped, and coverage (81%), then rejected the
changed fake-server fixture's old lock digest. The exact fixture review and prior
lock are retained here; only its active digest was updated. All required strict
router compatibility checks pass locally with the reviewed fixture.

Updated `tests/test_posix_guards.py`: `ea531187a2f7411050e6170de0bd466593a826ff046a198ddfed4052ab21e922`.
