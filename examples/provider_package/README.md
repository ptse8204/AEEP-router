# AEEP 0.6 provider-package fixture

This directory contains a deterministic signed package, independently attested
evidence, a local trust store, and no credentials. Regenerate it with:

```bash
PYTHONPATH=src python examples/provider_package/build_fixture.py
```

The lifecycle is:

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
