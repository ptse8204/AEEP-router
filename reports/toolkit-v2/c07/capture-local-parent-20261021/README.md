# Correct the local parent references

## Latest October21 result

These original proposal/execution records are historical. Source7707756 now passes
all12 integrated checks and16 current-wheel offline checks. The later approved
collector build failed BuildKit source resolution before image/worker/model creation;
the independent docs attempt stopped on a blank-line lint error, now fixed.
Continue only from [the local-tag/docs amendment](../capture-local-tag-20261021/README.md),
bundle3b10b05e…, after its requested approval. Never replay this terminal driver.
The original sections below retain their historical scope and counters.

The operator approved review70c19b6e…, and the one-shot control build failed before
creating an image. BuildKit interpreted the bare `FROM sha256:…` value as a Docker
Hub repository named `library/sha256`. It attempted a registry metadata lookup,
which failed. The raw log and failed build accounting are retained in
[the predecessor](../capture-image-repair-20261020/build-result.json). No image,
worker, collector or model started. No successful image pull is evidenced;
network traffic was not measured. This was an implementation error in the review.

The [exact reference amendment](operation-review.json), SHA-256
`8056e725cfb62949e4eb16f91bd7ad5a3e83c03ad296774af9ef227300e54bec`,
uses each parent's existing local repository name followed by its same immutable
`@sha256:…` digest. A read-only Docker inspection resolved both exact references
and found no ONBUILD instructions. The driver repeats those guards within its
reserved operation before building; missing or changed parents stop execution.
No parent tag is created, replaced or deleted.

The collector bytes, parent IDs, COPY target/mode, binaries, dependencies, model,
destination and four-turn ceiling are unchanged. The old attempt is terminal.
This review permits one fresh attempt with fresh output tags/records, followed by
one fresh conformance check and the already specified gated public diagnostics.
It has not been approved or executed. It does not authorize automatic retries,
source repairs, dependency changes, credential access, release or cleanup.

Docker documents `--network` as controlling RUN instructions and `--pull` as
requesting pulls; neither is a blanket source-resolution network boundary. See
[the official build reference](https://docs.docker.com/reference/cli/docker/buildx/build/).
No RUN exists in these two Dockerfiles. Actual BuildKit resolution of the corrected
references remains untested; the passed local inspection is not a build result.

The prior review explicitly says no automatic retry and pins different Dockerfile
bytes. [CONTINUATION.md](../../../../docs/aeep-toolkit/CONTINUATION.md#research-and-change-authorization)
also requires applicable authority for image provisioning. Retain actual explicit
approval in `operator-approval.json` with `approved: true` and `review_sha256` equal
to the raw hash above. Verify every input and absence of an execution marker, then
run once from `/Users/edwintse/Documents/aeep-toolkit-v2`:

```bash
PATH=/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH PYTHONPATH=src python3 reports/toolkit-v2/c07/capture-local-parent-20261021/run-repair.py 8056e725cfb62949e4eb16f91bd7ad5a3e83c03ad296774af9ef227300e54bec
```

Do not replay either failed predecessor, the completed wheel check, the completed
offline docs check or the original comparison. No full application regression is
needed for unchanged source. The prepared amendment's syntax and input checks
passed; its corrected build and collector boundary remain unqualified.
