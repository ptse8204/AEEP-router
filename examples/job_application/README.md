# AEEP 0.5 job-application sandbox proof

This proof uses a synthetic job index, resume fact set, application form, and
confirmation channel. It exercises 30 postings, three fake ATS families, three
duplicate canonical IDs, one ambiguous timeout, durable approval records, and
reconciliation without retry. It performs no network calls or real submissions.
Reports are written to `reports/v05/jobs/`.

```bash
PYTHONPATH=src python examples/job_application/campaign.py
PYTHONPATH=src python examples/job_application/campaign.py --check
```
