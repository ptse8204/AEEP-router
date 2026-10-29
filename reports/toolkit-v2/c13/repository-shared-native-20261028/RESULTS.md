# Actual shared-native bundle result

The operator approved exact bundle `17defe159` on October 29. Its first runtime
attempt ended at preflight because three nested script hashes were stale. The
outer bundle contained the current hashes; its preparation audit had overwritten
the conflicting map entries instead of checking the nested review independently.
The original preparation PASS is retained but did not establish composed
execution readiness.

No runtime marker, download, image build, worker or canary was created. Canonical
grant counters remained 13,304 operations, 3,755 model turns,
120,080.87940059323 seconds and $0. No allowance was refunded or reset.
The actual failed result and reconciliation remain separate records.

After verifying unchanged source, component pins, accounting and absence of
external side effects, the operator agent completed the two separately approved,
previously unstarted independent components:

- Corrected wheel `b3d9c5d0`, with 32 exact cached dependencies: 19 installed CLI
  and identity checks plus one retained capture-chain check passed. The installed
  normal CLI exported the expected shared-default program `1f099dfb`. Its private
  runtime and scratch were removed; no dependencies were downloaded.
- Cached pinned Lychee 0.24.2: the offline check passed for all 69 documents
  against the retained input hashes. Its unchanged private runtime was removed.

These results do not qualify the unbuilt Git image, add a repository case, prove
comparative usefulness or pass a release gate. The current pool stays at 64, with
77 cases still missing. Source `b09911a0` is unchanged and retains its completed
13 source gates; those checks are not repeated.

A new [runtime-only review](../repository-review-bindings-20261029/runtime-review.json)
corrects the nested pins and adds a recursive binding audit before dispatch. The
terminal one-attempt approval does not permit an automatic retry. The completed
package and docs components will not be rerun.
