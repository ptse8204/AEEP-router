# Quickstart example

See how an action becomes a routing decision, a result and an execution receipt.
This small text task lets you try the full local path before connecting an agent.

After [source installation](../../docs/ONBOARDING.md#start), run from the repository
root. No model account is needed. `route` previews the decision; `run` executes it.

[Documentation index](../../docs/README.md).

```bash
pip install -e .
aeep doctor -m examples/quickstart/aeep.yaml
aeep route text.stats -i '{"text":"one two"}' -m examples/quickstart/aeep.yaml
aeep run text.stats -i '{"text":"one two"}' -m examples/quickstart/aeep.yaml
python examples/quickstart/embed.py
```

Try `--policy quota_saver` with a small `context_tokens_remaining` value to see how capacity changes route rejection and scoring.

## Expected result and limits

The text `one two` produces 7 characters, 2 words and 1 line, with a verified
local receipt. The embedding example prints its selected executor, output and
measured resources. Use [guided setup](../../docs/ONBOARDING.md#start) when
you want to expose planning/search to an agent; this CLI demo does not do that.
