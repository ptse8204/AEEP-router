# GitHub default branch demo

Install AEEP and Git, then run from this repository checkout. Preview the
decision before executing and inspect the selected implementation. Public HTTP
needs network access; MCP and delegated alternatives need their own setup.

[Documentation index](../../docs/README.md).

This example chooses a route for one real action: finding a repository's default branch. The available routes use local Git, GitHub REST, GitHub MCP, two commercial subscriptions, or a browser delegate.

```bash
aeep route github.repository.default-branch@1 \
  --manifest examples/github/aeep.yaml \
  --input '{"repository":".","owner":"ptse8204","name":"AEEP-router"}' \
  --agent
```

The local Git route should win when the repository is already checked out. Run it with:

```bash
aeep run github.repository.default-branch@1 \
  --manifest examples/github/aeep.yaml \
  --input '{"repository":".","owner":"ptse8204","name":"AEEP-router"}' \
  --agent
```

The REST route works for public repositories. Configure the MCP command before enabling that route. Host and browser routes return instructions and require one terminal outcome report.

## Expected result and limits

Expect a decision naming the selected route and, after execution, the repository
default branch with a receipt. Selection depends on available Git metadata and
manifest constraints; a configured alternative is not proof that it is ready.
