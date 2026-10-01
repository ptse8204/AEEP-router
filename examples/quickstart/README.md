# Quickstart example

```bash
pip install -e .
aeep doctor -m examples/quickstart/aeep.yaml
aeep route text.stats -i '{"text":"one two"}' -m examples/quickstart/aeep.yaml
aeep run text.stats -i '{"text":"one two"}' -m examples/quickstart/aeep.yaml
python examples/quickstart/embed.py
```

Try `--policy quota_saver` with a small `context_tokens_remaining` value to see how capacity changes route rejection and scoring.
