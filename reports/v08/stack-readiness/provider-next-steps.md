# Remaining real onboarding evidence

The selected existing connections are Hugging Face and Figma. Their free host
identity checks succeeded, but the exposed responses did not include billing
readiness fields. The local Python version check succeeded through AEEP's setup
service. No generation call, payment change or new credential access occurred.

For the metered-service gate, Hugging Face Inference Providers is the preferred
next candidate because the host already exposes a Hugging Face connection.
[The official billing guide](https://huggingface.co/docs/inference-providers/pricing)
describes usage billing and directs the operator to account billing controls.
The [official Hub API reference](https://huggingface.co/docs/hub/api) links an
OpenAPI contract with `GET /api/whoami-v2`, whose schema includes `canPay` and
`billingMode`. These fields were absent from the host connector's cached response.
Do not infer their values from PRO membership or successful authentication.

An operator-owned API binding and a reviewed supported readiness mapping are
still needed for that credential-bound check. AEEP's generic HTTPS adapter reads
a reviewed numeric credit field; a provider-specific boolean billing flag needs
a reviewed host adapter mapping. No protected billing endpoint was called during
this documentation inspection. The operator can keep this gate pending without
blocking offline stack use. Secrets must stay outside model context.

A demonstrated host sign-in handoff remains a separate gap. Existing access
establishes connectivity at the check time; it does not demonstrate a newly
completed setup journey. Production generation, paid tasks and comparative value
assessment remain outside these observations.
