# Reproduce six cached suites with explicit runtime support

This batch prepares more real repository workloads for the usefulness and
selection studies. It reuses the existing AEEP assessment service, controlled
executor, source-bound grader and completed reproduction drivers. The current
pool remains39 cases; these six proposals add no model evidence or admission.

| Task | Origin and workload | Required identities | Fresh variants |
| --- | --- | --- | --- |
| MCP Python SDK222 | Upstream multi-file resource-handling repair | 55 | Reference, original, two per-file partial repairs |
| MCP Python SDK384 | Authored corrected-snapshot schema audit | 5 | Reference and regression |
| Goodconf51 | Authored corrected-snapshot config audit | 22 | Reference and regression |
| Twyn317 | Upstream multi-file reference-list repair | 43 | Reference, original, three per-file partial repairs |
| Dishka512 | Upstream single-file decorator repair | 15 | Reference and original |
| Prometheus Python1134 | Authored corrected-snapshot parser audit | 30 | Reference and regression |

These170 required identities include three authored preservation guards. The two
MCP snapshots belong to one repository group. No stage is frozen; no same-repository
origin may cross stages. If all six reproduce, the pool would reach45 snapshots
across29 repositories;96 further cases would still be needed. The existing39-case
pool and every earlier runtime binding remain unchanged.

## Exact execution review

[Approval bundle](approval-bundle.json), SHA-256:
`c81557a2e19233d728dfec9dd8449454041e00f01fee9ff5da8f95cc6e5943d0`.
It is prepared, unapproved and unexecuted. The completed five-repository approval
`be8b0e5f` is terminal and covers different artifacts; its unused slot cannot be
reused here. No architecture decision is pending.

One proposed private offline image installs22 exact cached support wheels,
4,451,951 bytes, on the retained parent:
`sha256:b0eb4add50887814206ad86dc0b685003382da55a44b166711438409769a9661`.
The output tag is `aeep-toolkit-v2/repository-grader:py313-cached-suites-20261027`.
These packages support the protected grader and stay optional; they are not
AEEP core dependencies. [The dependency review](runtime-support-review.json)
retains exact versions, artifact hashes, wheel tags, requirements and licenses.
No project installer, resolver, OS package or host installation runs.

The driver binds the actual output digest before source tests, checks inherited
configuration and layers, and retains the image. At most20 offline calls run:
three fresh containment/state/version probes plus17 frozen variants. The envelope
is23 existing-grant operations,1030 reserved seconds,zero model turns and cash.
The reservation sum is180 build +30 setup +120 analysis +20 ×35 per call, including
wrapper margins. The existing hard budget guard checks every reservation. The
192MiB image-growth cap and50GiB host reserve are operation controls, not product
resource acceptance targets.

Independent cases continue after an isolated incompatibility only when canonical
completion, accounting and cleanup are verified. Common uncertainty stops further
dispatch. No automatic retry is permitted. Bounded public-test replies, receipts,
attempts and all charges remain. Only new attempt-owned containers and the
unchanged nonsecret canary are removed. All existing images and volumes remain.
No models,cash,execution-time downloads,pulls,credentials,new external services or
destinations,package/docs reruns,activation,publication or release are included.
Upstream subprocess/local fixtures stay inside the offline container, without
published ports or host services.

## Explicit adaptations and exclusions

Asyncio/AnyIO, coverage and benchmark plugins are declared per case. Automatic
pytest plugin loading remains disabled. All170 required identities and original
assertions remain. The private guards distinguish an audit's unchanged correct
snapshot from unnecessary source edits; they do not create upstream benchmark
results or useful-capability labels.

Goodconf's [source profile](source-profile-review.json) applies the published `-s`
capture option equally before grading, retaining `--cov --cov-branch`. Its upstream
Python answer remains unchanged until reference preparation. Unexecuted CI runner/
matrix and ignored-lockfile edits are omitted explicitly; original metadata and
omitted section hashes remain. All upstream test patch assertions are identical.
This is a bounded authored runtime adaptation, not an official upstream score.

Dishka and Prometheus failed earlier reproduction without applicable plugin
support. Those results and charges remain unchanged. This new runtime does not
prove the exact old exception cause. CanvasAPI stays excluded after its terminal
collection error; this review does not repeat it. PyGLS remains deferred for its
decorated collection hook and fixture-scope profile. Its three support wheels were
reviewed as inert bytes but are not selected for installation. MCP1864 requires a
bounded serial profile and is not included.

An unexecuted first preparation exposed the missing scope/profile and plugin
handling. Its manifest and logs are retained. The current six-case preparation
has no errors. No subject code was imported into the coordinator.

## Verified preparation

[Preparation checks](preparation-checks.json) passed30 grader guards,22 classifier
checks and140 asset bindings. [Pure review derivation](static-bundle-audit.json)
checked the new image/environment/request binding in a labelled temporary
synthetic fixture, then removed it. That fixture grants no execution authority.
[Final checks](final-preparation-audit.json) verified plugin declarations,170
required identities,seven budget guards,probe/driver syntax,source stability and
the parent environment/image binding. No new build, install, container or model
turn has occurred. Product source remains `4cb0bf74`; its completed source and
installed-wheel checks are not repeated.

## Resume after actual exact approval

Inspect markers and the actual response. If approved, record it once in
`operator-approval.json`, check the current grant/expiry and free space, then run
once from the repository root:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 reports/toolkit-v2/c13/repository-supported-suites-20261027/run-bundle.py c81557a2e19233d728dfec9dd8449454041e00f01fee9ff5da8f95cc6e5943d0
```

Reopen canonical terminal evidence and cleanup before consolidating any new case.
No comparison, qualification, selection or resource-acceptance gate closes from
these reference observations. Do not replay `be8b0e5f`.
