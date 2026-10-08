# AEEP 0.5 job-application sandbox proof

Check that an uncertain submission stops for recovery instead of being submitted
again. This local sandbox lets contributors inspect approval, duplicate protection
and reconciliation using fake jobs and applicants.

Install AEEP and run from the repository root. Start with `--check` to validate
the retained report; the command without it regenerates historical output files.

[Documentation index](../../docs/README.md).

This proof uses a synthetic job index, resume fact set, application form, and
confirmation channel. It exercises 30 postings, three fake ATS families, three
duplicate canonical IDs, one ambiguous timeout, durable approval records, and
reconciliation without retry. It performs no network calls or real submissions.
It writes reports to `reports/v05/jobs/`.

```bash
PYTHONPATH=src python examples/job_application/campaign.py --check
```

## Expected result and limits

A successful check confirms the retained synthetic safety gates. It establishes
no real submission or hiring outcome. See the
[sandbox design](../../docs/JOB_APPLICATION_DEMO.md) for the approval boundary.

## Regenerate synthetic reports

Use a separate checkout to preserve the retained reports before running:

```bash
PYTHONPATH=src python examples/job_application/campaign.py
```
