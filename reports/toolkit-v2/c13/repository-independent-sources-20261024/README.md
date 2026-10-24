# Prepare five more independent repository workloads

The corrected six-turn development journey is complete. The next step is to
check whether five additional task contracts reproduce reliably in the protected
grader. This adds repository diversity to the provisional pool before the formal
usefulness and selection evaluations. It does not require another engine or a
change to the local CLI/report architecture.

| Repository task | Workload | Required identities | Runtime scope |
| --- | --- | --- | --- |
| MSAL Python 795 | Authored audit of the published corrected snapshot | 30 | Mocked identity responses; no sign-in, host credentials or external HTTP |
| SQLacodegen 370 | Published single-file relationship-generation repair | 46 | Existing declared SQLite tests; no PostgreSQL/MySQL service |
| LM Studio Python 110 | Published single-file KV-config repair | 22 | Pure configuration tests; no LM Studio server or model |
| Model Bakery 520 | Published single-file timestamp-generation repair | 191 | Upstream in-memory SQLite setup; explicit pytest-django plugin |
| CanvasAPI 716 | Published single-file date-handling repair | 62 | Original mocked HTTP tests; network denied |

These are five distinct repositories and snapshots, not five model observations.
The MSAL audit is an authored control with a private byte-preservation guard; the
other four retain upstream issue and preservation assertions. No case is adopted
or assigned to a frozen stage. If all five reproduce, the provisional pool would
reach 40 cases; the planned balanced stages would still need 101 more. Repository
groups must stay within one stage, and development repositories remain excluded.

## Exact next execution review

[Approval bundle](approval-bundle.json), SHA-256:
`be8b0e5f2d7b3ebf7f3c212dea8f7e7e754970eb7ff1c9df1aa8ba7d1f81ab6b`.
It is prepared and unapproved. No new image, installation, container, model turn
or upstream test execution has occurred under this review.

The review permits one private offline image build from existing parent
`sha256:324a1fee6ee58475ecfdc659c98be5b5a8480fae4389b26b13b5b0b43bc32d2b`.
Sixteen exact cached wheels, totaling 3,373,581 bytes, supply the reviewed runtime
closure. The output tag is
`aeep-toolkit-v2/repository-grader:py313-repository-supports-20261024`.
The driver binds its actual image digest before testing and retains it for the
remaining work. No existing image is removed or replaced.

At most 13 offline calls run: three fresh containment/state/version probes, then
five reference/counterexample pairs. The ceiling is 16 existing-grant operations,
785 reserved seconds and zero models or cash. The reservation sum includes
180 build + 30 setup + 120 analysis + 13 × 35 per call, including wrapper margins.
The same hard review-budget guard checks every reservation across both phases.
These are temporary execution caps, not production resource requirements.

Independent cases may continue after an isolated incompatibility once completion,
accounting and cleanup are verified. Common authority, binding, accounting or
cleanup uncertainty stops dispatch. No automatic retry is permitted. Bounded raw
replies and canonical receipts/attempts remain; only new owned containers and the
unchanged nonsecret canary are removed. There are no downloads during execution,
pulls, OS packages, project installers, host installation, credentials, new
services/destinations, package/docs reruns, activation, image deletion or release.

The existing AssessmentService, ContainerExecutor, repository-suite adapter and
completed batch drivers are reused. The 16 supports are private optional grader
dependencies; they do not become toolkit core requirements. The exact package,
version, artifact hash, Linux/portable wheel tags, license text and active
requirements are in [the runtime review](runtime-support-review.json). Static
closure is not a runtime pass.

## Preparation evidence and exclusions

[Preparation checks](preparation-checks.json) passed 25 first-party grader guards,
22 classifier cases and 108 artifact bindings. The
[pure derivation check](static-bundle-audit.json) checked the image-bound request,
environment and amendment in an explicitly synthetic temporary directory, then
removed it. That fixture provides no execution authority. Probe Python parses,
including its JSON literal, and the seven hard budget guard fixtures passed.
Product source remains `4cb0bf74`; its 1,679-test source gates and installed-wheel
check are unchanged and are not repeated here.

Read-only collection retrieved 4,594,587 source bytes across 19 snapshots and
3,373,581 wheel bytes. No downloaded code was imported. Thirteen source/patch
AST audits completed; Twine remained unresolved, three Cyclopts archives exceeded
the transport bound, and Scuba/OctoDNS hit protected-path rules. These are not
failed model tasks. Other SQLacodegen snapshots need external database fixtures;
PyGLS needs additional protocol/transport support; Sphinx-Issues and Valohai need
unreviewed dependency closures. They were not included by guessing compatibility
or dropping assertions.

Two preparation defects were corrected before this review was frozen: the
pytest-subtests entry point is `pytest_subtests.plugin`, and the host canary uses
its own control directory rather than the existing source-cache directory. The
unexecuted draft manifest and failed first-party preparation logs are preserved.
A later report-only correction copies explicit plugins from protected truth into
the case summary; it changes no task, payload, test byte or execution permission.
The initial source audit also omitted `PYTHONPATH=src`; its import failure is
retained separately. None consumed a grant operation or executed subject code.

## Resume only after actual exact approval

Inspect existing markers and the actual user response first. If approved, record
that response once in `operator-approval.json`, then execute once from the repo
root:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 reports/toolkit-v2/c13/repository-independent-sources-20261024/run-bundle.py be8b0e5f2d7b3ebf7f3c212dea8f7e7e754970eb7ff1c9df1aa8ba7d1f81ab6b
```

Reopen terminal results, attempts, receipts, usage and cleanup before consolidating
any accepted cases. No unused slot from this or a prior review authorizes a replay.
The completed six-turn results remain in the
[development comparison](../repository-task-delivery-20261023/comparison.md).
