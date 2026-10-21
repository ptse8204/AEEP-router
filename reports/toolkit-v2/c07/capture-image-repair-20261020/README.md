# Correct the collector file in the two worker images

The approved capture check stopped before Codex initialization. Both images contain
collector `bb758886…`; the reviewed profile requires `d551e2f4…`. The immutable
launcher rejects the mismatch. The source audit and failed operation are retained
in [the failure analysis](../capture-repair-20261019/collector-failure-analysis.json).
No diagnostic model turn ran. The original study remains unchanged.

[The exact repair review](operation-review.json), SHA-256
`70c19b6eb98a0b8c3878200243fb01a4e4f288a83b01369649ce09700e9204be`,
is prepared and has not been approved or executed. It specifies two local
COPY-only builds from the old immutable parents. Each replaces only the collector
with the already-reviewed source and mode 0444. There is no RUN instruction,
installation, image pull, new model destination or source change. Parent and
rollback images remain intact.

The reviewed driver records the resulting image IDs, then freezes fresh exact
worker definitions under standing authority. It runs one new isolation check;
only a passed check permits the explicit-request diagnostic pair. Positive bound
instruction loading and complete token captures must precede the optional pair.
The total ceiling remains four task turns. A failure stops dependent work and is
retained without automatic retry. This is capture verification, not a new value
study or admission decision.

The governing boundary is
[CONTINUATION.md](../../../../docs/aeep-toolkit/CONTINUATION.md#research-and-change-authorization):
image provisioning needs applicable authorization. The approved predecessor also
explicitly excluded builds and replay. Its approval cannot cover this correction.

After explicit approval, retain the actual human wording in `operator-approval.json`
with `approved: true` and `review_sha256` equal to the raw review hash above. Verify
`preflight.json`, every input pin and absence of `execution-started.json`, then run
from `/Users/edwintse/Documents/aeep-toolkit-v2`:

```bash
PATH=/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH PYTHONPATH=src python3 reports/toolkit-v2/c07/capture-image-repair-20261020/run-repair.py 70c19b6eb98a0b8c3878200243fb01a4e4f288a83b01369649ce09700e9204be
```

Never replay `capture-repair-20261019/run-collector.py`, the completed package
installation driver, or the completed link checker. No new broad regression or
wheel build is needed for unchanged application source. The next operator approval
covers these exact COPY-only recipes and derived checks; it does not authorize
credential access, more than four task turns, release or cleanup of retained images.
