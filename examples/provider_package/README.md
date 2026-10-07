# AEEP 0.6 provider-package fixture

For operators learning the package lifecycle. Install AEEP and run from the
repository root. Start with `provider verify`; it should validate the fixture
and its evidence without activating a route. Later commands change the local
router database. Regenerating the fixture rewrites signed assets, so it is
separate from verification. Its public test keys are not production trust.

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
