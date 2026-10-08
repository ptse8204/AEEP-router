# AEEP 0.6 provider-package fixture

Follow a shared capability from package verification to approved local use.
This fixture shows how an operator can inspect signed artifacts, test the route
and explicitly activate it.

Install AEEP and run from the repository root. Start with `provider verify`;
it checks the package without activating a route. Later commands change the
local database. Regeneration rewrites signed assets, so keep it separate from
verification. The public test keys are not production trust.

[Documentation index](../../docs/README.md).

This directory contains a deterministic signed package, independently attested
evidence, a local trust store, and no credentials.

Verify, ingest and inspect the package, then run smoke checks, qualify it and activate it:

```bash
aeep provider verify examples/provider_package/aeep-provider.yaml \
  -m examples/provider_package/aeep.yaml
aeep candidate ingest examples/provider_package/aeep-provider.yaml \
  -m examples/provider_package/aeep.yaml
aeep candidate inspect fixture.command.text-statistics -m examples/provider_package/aeep.yaml
aeep candidate smoke fixture.command.text-statistics -m examples/provider_package/aeep.yaml
aeep candidate qualify fixture.command.text-statistics --reuse-evidence \
  -m examples/provider_package/aeep.yaml
aeep candidate activate fixture.command.text-statistics -m examples/provider_package/aeep.yaml
```

## Expected result and limits

Verification leaves the package inert. Only the explicit smoke, qualification
and activation sequence can make the fixture route eligible. Read
[provider packages](../../docs/PROVIDER_PACKAGES.md) for wire-version and
[evidence reuse](../../docs/EVIDENCE_REUSE.md) for applicability rules.

## Regenerate the package fixture

Use a separate checkout to preserve the retained signed assets before running:

```bash
PYTHONPATH=src python examples/provider_package/build_fixture.py
```
