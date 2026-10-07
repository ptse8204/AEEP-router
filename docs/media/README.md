# AEEP walkthrough recording

[27-second MP4](aeep-demo.mp4) or view the [animated preview](aeep-demo.gif).
Recorded on October 5, 2026 in a dedicated macOS Terminal window, using the
installed AEEP runtime. The video is cropped to terminal content and trimmed;
output is real. `jq` selects fields for readability. No model turn or paid API
call runs in this demonstration.

The recording used the installer-managed runtime and default manifest. Its
exact commands are below. For a source installation, activate the environment
from [setup](../ONBOARDING.md#start), omit the `export PATH` line, and pass
`--manifest examples/quickstart/aeep.yaml` to each route/run command. That fixture
selects `python.text-stats` rather than the recording's `builtin.text-stats`.
Run from the repository checkout:

```bash
export PATH="$HOME/.local/share/aeep/venv/bin:$PATH"

aeep route text.stats --input '{"text":"hello world"}' --agent |
  jq '{capability, selected, reason, alternatives: [.alternatives[].executor_id]}'

aeep run text.stats --input '{"text":"hello world"}' --agent |
  jq '{ok, output, receipts: [.receipts[] | {receipt_id, executor_id, status, valid, monetary_usd: .resources.monetary_usd}]}'

python examples/stacks/demo.py
```

`jq` is optional: omit each pipe to see the complete JSON response.

The first command selects `builtin.text-stats`, with command and host alternatives.
The second returns 11 characters, 2 words and 1 line, plus a successful verified
receipt with zero cash usage. Receipt IDs and timing measurements vary by run.
The last command completes three synthetic stacks: media (9 nodes), data (4),
and research (4). Each node produces a receipt. These are offline fixtures: the
media fixture produces an edit timeline, and research uses fixed source text.
They do not demonstrate provider onboarding, paid generation or comparative benefit.

For a host connection, follow [guided setup](../ONBOARDING.md#start) and its
public catalog-search prompt. A new connection allows planning and search;
executing an action requires its separate authority. The recording shows the CLI.
