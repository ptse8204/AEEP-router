# Review a proposed toolkit installation

Preview the components and permissions before changing your machine. The toolkit
now lists three profiles and checks explicitly selected artifact manifests. It
performs no installation, network lookup, host configuration read or activation.

Run from the source checkout without installing a package:

```bash
PYTHONPATH=src python3 -B -m aeep_toolkit list essentials
PYTHONPATH=src python3 -B -m aeep_toolkit list evaluation
PYTHONPATH=src python3 -B -m aeep_toolkit list full
```

The catalog contains pinned source-review records. Its entries remain blocked
until exact package artifacts, complete dependencies and applicable runtime
checks are available. A repository commit does not identify a built package.
Full shows the choices; it selects nothing automatically.

For operator-prepared metadata, supply a C02 extension registry and a preview
policy explicitly. The paths below are placeholders for your own reviewed files:

```bash
PYTHONPATH=src python3 -B -m aeep_toolkit plan essentials \
  --registry registry.json --policy preview-policy.json --select evaluator-id
```

`--select` can be repeated. Dependency manifests must match their declared
canonical hashes. Output includes each complete manifest, dependency order,
license/data restrictions, permissions, resources, effects, rollback and supplied
installed/enabled observations. Missing observations stay unknown. Every selected
component's complete artifact/dependency inventory needs an explicit review in
`reviewed_dependency_manifests`; this records metadata review, not execution
approval. Policy lists are exact allowlists and default to no acceptance.

The command exits 2 when blocked, and 0 when ready for review. Neither status
installs anything or grants permission. There is no toolkit apply command yet;
the existing legacy setup command is not a substitute for the missing V2 artifact
lock. Enabling a disabled component or replacing different installed bytes needs
a separate effect review. Unknown disk/memory and a projected breach of the
50 GiB free-space reserve block the preview. Memory is shown per component; no
aggregate runtime measurement is inferred.

Schemas are `toolkit-preview-policy.schema.json`,
`toolkit-installed-observation.schema.json` and
`toolkit-installation-preview.schema.json`. The CLI accepts metadata files up to
1 MiB and suppresses parse values in error messages. It never inspects passwords,
authentication files or arbitrary plugin configuration. Use Python's `-B` option
as shown to suppress interpreter bytecode-cache writes as well.

The preview fixture under `tests/fixtures/toolkit` is synthetic software evidence.
It does not establish installation readiness for any real evaluator.
