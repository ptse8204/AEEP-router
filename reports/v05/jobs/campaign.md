# AEEP 0.5 job-application sandbox proof

- PASS — zero-unapproved-submissions: every synthetic submit has a durable approval record
- PASS — zero-duplicate-submissions: 30 postings canonicalized to 27 unique jobs before submission
- PASS — zero-unsupported-resume-facts: 2 referenced fact(s) are approved
- PASS — indeterminate-reconciled-before-retry: synthetic timeout was reconciled without a second submit
- PASS — one-receipt-per-execution: 81 receipt(s)
- PASS — all-synthetic-postings-and-form-families-covered: 30 postings, three fake ATS families, and three duplicate canonical IDs
- PASS — zero-real-writes-captcha-email-or-pii: in-memory executors used pseudonymous IDs; no network, CAPTCHA, email, credential, or real PII
