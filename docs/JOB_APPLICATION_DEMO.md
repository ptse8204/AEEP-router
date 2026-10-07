# AEEP 0.5 job-application sandbox

For contributors inspecting a synthetic end-to-end approval and recovery
fixture. Use the [example instructions](../examples/job_application/README.md)
to check retained artifacts. This is a sandbox design, not an application-submission
service or evidence about real hiring outcomes.

[Documentation index](README.md).

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
