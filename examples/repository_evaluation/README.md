# Pinned repository development examples

Use these examples to check the repository patch grader before preparing a real
capability comparison. They cover a known CLI regression, a seeded cross-file
accounting fault and a working callback contract that needs no change.

`development-cases.json` retains exact AEEP revision/file hashes, Apache-2.0
provenance, public inputs, protected checks and reference patches. Send only its
`input` object to a task worker. These extracted examples are known to the
implementer and cannot supply independent holdouts or live benefit evidence.

From the repository root:

```bash
PYTHONPATH=src python3 scripts/prepare_repository_development_cases.py
PYTHONPATH=src python3 -m aeep_toolkit.cli repository-recipe \
  --cases examples/repository_evaluation/development-cases.json
```

Both commands print metadata; neither launches a model, executes candidate code
or installs software. The first reads pinned local Git objects and reconstructs
the exact checked-in examples. The second exports the existing reviewed recipe
contract. Its development generator refuses to create qualification/holdout cases.

See the [evaluation guide](../../docs/aeep-toolkit/REPOSITORY_EVALUATION.md) for
containment requirements, comparison controls and selection-scoring limits.
