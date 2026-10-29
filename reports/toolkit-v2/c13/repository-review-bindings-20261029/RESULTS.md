# Actual runtime-only result

The operator approved exact review `a11807f2`. Its single attempt downloaded the
reviewed Git archive, verified its size, hash and copyright, and prepared the
context. It then failed the expected-library guard: actual ELF dependencies also
include `ld-linux-aarch64.so.1`, which was absent from the three-name expectation.

One canonical operation is complete and remains charged:
2.9479576251469553 seconds. The grant now records 13,305 operations, 3,755 model
turns, 120,083.82735821838 seconds and $0. There was no refund or reset. No Docker
build was invoked, no output image exists, no worker started and no canary was
created. All images and existing containers remain untouched.

The exact successful-request count is unknown because the local attempt list was
lost when the guard raised. The reviewed code bounded requests to two. The
retained archive's 8,665,568 bytes and SHA-256 match the approved artifact; the
19 prepared context files, modes and copyright also match. Do not infer a precise
request count from elapsed time.

[Terminal reconciliation](terminal-reconciliation.json) retains the canonical
operation and actual failure. A subsequent read-only image audit verified the
loader and other required libraries in the same parent without running Linux
code. The unchanged owned export and scratch were removed. No library is added.

The new [cached-only review](../repository-cached-git-20261029/runtime-review.json)
uses the unchanged archive/context and verifies the four actual dependency names.
It needs a fresh exact approval; the terminal review forbids automatic retries.
The 20 installed checks, offline docs check and 13 source gates remain complete
within their retained scopes. They are not repeated. The provisional pool stays
at 64 and comparative usefulness remains unproven.
