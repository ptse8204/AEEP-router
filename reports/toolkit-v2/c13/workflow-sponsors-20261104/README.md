# Resolve the source repository's GitHub Sponsors link

The ordinary toolkit export preview now verifies an explicit Sponsor review and
the exact funding declaration against the selected candidate source. It shows
the GitHub Sponsors link when the funding file names that source repository's
account. The existing supplied developer assertion stays available with its
original trust label.

The [source-bound preview](preview.json) uses the [pinned Ponytail funding file](https://raw.githubusercontent.com/DietrichGebert/ponytail/1d95ff7d39de12d87014ea40d4e22201bddc501b/.github/FUNDING.yml).
Its SHA-256 matches the prior C12 source review. The input has zero task runs
and the output remains `NOT_ASSESSED`. The preview verifies declaration and
byte binding. Legal identity, live Sponsors eligibility and payment remain
outside its evidence.

```bash
PYTHONPATH=src python3 -m aeep_toolkit export-preview \
  --evidence reports/toolkit-v2/c12/developer-source/no-observations.json \
  --disclose-source \
  --sponsors-review reports/toolkit-v2/c13/workflow-sponsors-20261104/sponsors-review.json \
  --reviewed-digest d072b1586a4bf601739a88552ab6c449bfe05a0e03541b389b72e77adb113c13
```

The focused CLI checks cover disclosure, source drift, funding drift, review
drift and a funding declaration naming a different account. The full source
checks are recorded separately. This work does not rerun any Ponytail task.

## Verification

All 13 source checks passed with 2,135 tests and 21 skips in each full run.
Coverage was 82.69755801607766%, with both branch gates passing. The source
snapshot includes the separate local CI test and development pin for
reproducibility. Those edits stay outside the feature commit.

The [verification summary](verification-summary.json) binds the exact wheel,
installed source and checked docs. The retained private runtime passed the
installed Sponsors preview, schema and review drift checks. Its sandbox
denied the tested outside read, outside write and network operations.
