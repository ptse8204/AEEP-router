# AEEP 0.5 job-application sandbox

The job proof is a deterministic safety campaign, not a planner or live job
submission feature.

```bash
PYTHONPATH=src python examples/job_application/campaign.py
PYTHONPATH=src python examples/job_application/campaign.py --check
```

It uses synthetic postings, a fake ATS/mailbox/fact set, structured resume plans,
and local routes. The irreversible submit capability is a distinct WRITE route
with an immutable approval record. Its idempotency key binds pseudonymous job
and applicant identities, resume digest, and revision. A synthetic timeout is
marked indeterminate and reconciled without a second submit.

No credentials, real PII, public websites, recruiter mail, CAPTCHA bypass, or
real application submission are used by CI or the default example.
