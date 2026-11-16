# Waza local runtime continuation

Approved review `25d22dca` downloaded and verified the exact archive and all
five model blobs. Setup stopped on the first dynamic-library symlink. The
archive lists ten relative aliases inside the runtime directory, and the
partial install ends immediately before the first alias. The first extractor
accepted only regular files and directories. The binary and child already
present in the partial tree independently passed their strict signature
checks.

The [terminal result](initial-result.json) retains the single setup charge
of 57.780 seconds. Service startup, model inference and grading were
unstarted. Both the downloaded artifacts and the original partial tree remain.
The [original approval](initial-operator-approval.json) binds the terminal
attempt.

## Exact follow-up

Review [`d5b47cc8`](continuation-review.json) reuses the downloaded bytes.
The [archive inventory](archive-index.json) identifies every member by kind
and hashes all regular files. The continuation accepts only those ten
audited library aliases. They must resolve within the new runtime to regular
library files. It writes regular files before creating aliases and verifies
the signed program and runner. The continuation then calls the existing
bounded Waza and Ollama driver for the previously unstarted work.

The [first-party preflight](continuation-preflight.json) passed 24 input
bindings, archive controls, sandbox and listener checks, the single-request
gateway, both grading outcomes and exact reservations in a copied ledger.
The library test covered an out-of-order alias chain and rejected absolute,
escaped, cyclic and unresolvable links. No runtime process or model ran
during preflight.

The follow-up needs one additional setup operation beyond the first review's
cumulative ceiling. Its four new operations include corrected extraction,
service readiness, one local completion and one protected grade. Its maximum
reservation is 465 seconds, with zero downloads, remote model calls and
cash spending. The earlier settled charge is preserved. The review expires
November 18 at 9:15 p.m. Vancouver time.

After explicit approval, revalidate the executable review copy at
`.aeep/waza-ollama-20261115-retained-continuation/operation-review.json`,
then use [the continuation driver](resume.py). The first-party preflight
leaves the live attempt unstarted. C13 remains at 37 of 39 and comparisons
remain paused.
