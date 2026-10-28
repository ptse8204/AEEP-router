# PyMdown portable-wheel correction — prepared, not executed

This review supplies the missing runtime dependency to the two pending single-file
PyMdown tasks without building another image or installing software. The existing
grader ZIP-loader puts the exact cached Markdown 3.9 wheel on a private Python
search path. A fresh probe must verify its actual origin, version, module hash
and rendering behavior before any task runs.

The failed predecessor is preserved in the
[actual issue-behavior results](../repository-issue-behavior-20261028/RESULTS.md).
Markdown was cached in a broad support review but excluded from the selected image
install manifest. Cache presence did not establish installation. No Markdown import
was observed in that failing probe. Both Xsdata tasks subsequently reproduced using
the explicitly approved report-control allowance; their results are not rerun here.

## Exact scope

The only added software is the cached 107,441-byte `markdown-3.9-py3-none-any.whl`,
SHA-256 `9f4d91ed810864ea88a6f32c07ba8bee1346c0cc1f6b1f9f6c822f2a9667d280`.
[The wheel review](portable-wheel-review.json) retains its BSD-3-Clause license,
publisher pin and explicit ZIP-loading mode. Static inspection verifies a pure
wheel and no active dependencies for Python 3.13 without extras. No download,
installer, image modification or host/project activation is planned.

PyMdown 2576 and 2807 retain the exact input, source, protected tests, reference,
fault artifacts, plugins and all 765 original identities/assertions. Each task still
changes one functional file and preserves version metadata. [Scope checks](scope-check.json)
confirm that all four payloads change only by the additional wheel; source/test
archives remain byte-identical. Twelve synthetic actual-grader guards passed.
They are preparation evidence, not reproduced tasks or benchmark results.

[The combined execution review](approval-bundle.json) permits one fresh portable
runtime probe and four reference/original variants on retained image 9f473c49.
Maximum seven offline calls, eleven existing-grant operations and 545 reserved
seconds includes at most two recorded same-software report-control calls and one
extra setup/analysis phase. Initial scope: five calls, seven operations and 325
reserved seconds. These are finite execution limits, not production resource SLOs.

Zero models and cash. No builds, installations, downloads, credentials, services,
new destinations, activation, release, image deletion or uncertain replay. Keep
50 GiB free and all images. Remove only new owned containers, unchanged canary and
unchanged private docs-checker runtime. Retain canonical receipts, terminal failures,
all charges and at most 8 KiB of each failed public log. Common authority, identity,
accounting or cleanup uncertainty stops dispatch; no allowance refund or reset.
Cached offline docs checks the changed active status files. Existing source and
package checks are reused; the unchanged collector terminal fixtures are explicitly
reused with matching control-file hashes.

## Resume

Pool 60/38 repositories/3,186 identities and its 81-case gap remain unchanged.
No task under this review has run. Qualification, comparative usefulness, selection,
resource, human-control and release gates remain open. Current grant counters:
13,247 operations, 3,755 turns, 119,967.44845863385 seconds and 0.0 cash.

Obtain one exact execution approval, record the actual response, then run
`PYTHONPATH=src python3 reports/toolkit-v2/c13/repository-pymdown-portable-20261028/run-integration-bundle.py <approval-bundle-file-sha256>`
once from this checkout. Reopen canonical evidence and reconcile cleanup/accounting
before consolidating only actual eligible cases. All earlier thirteen operations
and 24.90588324982673 seconds stay charged. The f18daa4a software/payloads were
immutable; unused slots do not cover this added wheel. The user continuation
reserves untrusted execution and CONTINUATION.md requires applicable container
authority. No architecture, budget, image or installation decision is needed.
