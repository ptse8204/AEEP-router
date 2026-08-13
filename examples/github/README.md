# GitHub default branch demo

This example routes one real action across local Git, GitHub REST, GitHub MCP, two commercial subscriptions, and a browser delegate.

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
