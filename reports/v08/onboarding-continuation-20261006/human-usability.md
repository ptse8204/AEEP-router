# First-time tester exercise — pending

This is the remaining human gate, not a record of a completed test. Scripted
terminal checks establish that the prompts and commands run; they cannot tell us
whether a first-time user understands them.

Use an isolated account or test project and the built candidate in
`dist/v0.8.2-onboarding-continuation`. The public download command remains
unavailable until release publication. The tester should use only README.md,
docs/ONBOARDING.md and CLI help. Record the OS, architecture, candidate hash and
agent version. Leave credentials with the host; do not record sign-in output.

| Task | Passing observation | Actual observation |
|---|---|---|
| Install and select an available agent | The tester reaches setup checks without editing a manifest, activating a venv or copying schemas | Pending |
| Explain the two default catalogs | The tester identifies searchable metadata and understands that third-party plugins were not installed | Pending |
| Add a supplied local or public marketplace | The new source appears in the catalog list and a search returns its matching metadata, or explains a source failure | Pending |
| Request the tutorial-video comparison from the connected agent | Named, sourced components cover all seven stages; setup gaps and unknown quality are clear | Pending |
| Deny one tool for the selected connection | The access view reports denial, a subsequent call is blocked, and other connections remain unchanged | Pending |
| Explain access boundaries | The tester distinguishes native controls, AEEP calls, unmanaged alternatives and pending reload | Pending |
| Restore the rule and disconnect | The tool is restored after the required reload; disconnect succeeds while unrelated configuration survives | Pending |

Record where the tester asks for help, enters an unexpected command or misreads
an access state. Report those observations directly. Do not infer comprehension
from a successful command, or hide interventions behind a passing result.
