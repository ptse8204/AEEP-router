# Claude Code notes

Follow `AGENTS.md`. The fastest integration smoke test is:

```bash
pip install -e .
aeep init /tmp/aeep.yaml
python -m aeep serve --transport stdio --manifest /tmp/aeep.yaml
```

Use `aeep route` before `aeep run` when evaluating a new manifest. Never approve write/destructive/financial routes merely to make a test pass; define an explicit test policy and approval boundary.
