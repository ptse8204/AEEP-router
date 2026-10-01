# Claude Code notes

Follow `AGENTS.md`. Run this short integration smoke test:

```bash
pip install -e .
aeep init /tmp/aeep.yaml
python -m aeep serve --transport stdio --manifest /tmp/aeep.yaml
```

Use `aeep route` before `aeep run` when evaluating a new manifest. Define the test policy and approval boundary before execution. Never approve write, destructive or financial routes just to make a test pass.
