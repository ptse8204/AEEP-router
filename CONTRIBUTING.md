# Contributing

You can contribute adapters, benchmarks, policy research, security reviews, or
real execution traces with sensitive data removed.

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
4. Fail safely; never fall back silently.
5. Do not make one provider's token a universal currency.
6. Protocol objects remain provider-neutral.
7. New execution boundaries require explicit security analysis.
8. Tests must exercise real behavior, not only object construction.

## Pull requests

Describe the problem, your design, and the alternatives you considered. Explain
any compatibility or security impact and record the tests you ran. Update the
documentation and specification when the change affects them.

Keep provider-specific logic in adapters/integrations so the core scorer stays
independent of any model vendor, payment rail, or marketplace.

Read the [assessment testing policy](docs/ASSESSMENT_TESTING.md) before changing or running
assessment, execution-adapter or release-verification work in this repository.

## Stack changes

Read [STACK_PLANNING.md](docs/STACK_PLANNING.md) and
[ADR-011](docs/adr/ADR-011-stack-synthesis-preflight.md) before extending the planner
or setup boundary. Keep planning inert and keep vendor behavior in adapters.
Record exact implementation reviews, tests and remaining gates in
`reports/v08/plan-coverage.md`. Run the repository checks plus the stack fixture
suite. A mocked provider check cannot satisfy the real onboarding gate.
