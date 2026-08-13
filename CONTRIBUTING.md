# Contributing

Contributions are welcome, especially adapters, benchmarks, policy research, security review, and real execution traces stripped of sensitive data.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,http-server]'
PYTHONPATH=src python scripts/generate_schemas.py --check
pytest
coverage run -m pytest
coverage report -m
```

## Principles

1. Preserve raw resource measurements.
2. Hard constraints precede scoring.
3. Every selection must be explainable.
4. Safe failure beats silent fallback.
5. Do not make one provider's token a universal currency.
6. Protocol objects remain provider-neutral.
7. New execution boundaries require explicit security analysis.
8. Tests must exercise real behavior, not only object construction.

## Pull requests

Include:

- problem statement;
- design and alternatives;
- compatibility impact;
- security impact;
- tests;
- documentation/update to the spec when applicable.

Keep provider-specific logic in adapters/integrations. Do not couple the core scorer to one model vendor, payment rail, or marketplace.
