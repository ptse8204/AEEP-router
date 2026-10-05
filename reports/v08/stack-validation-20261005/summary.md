# Stack validation — October 5, 2026

Software validation passed on the implementation extending base revision
`db0d854215e227ab003b584b18a6cc3408c2eb83`. Changes remain in the working tree.
The [source index](source-index.json) records 146 implementation and new-test
file hashes; all matched after the final runs.

| Check | Result |
|---|---|
| Full pytest | 1,266 passed, 21 skipped |
| Full pytest under branch coverage | 1,266 passed, 21 skipped |
| Overall coverage | 82%; required critical and assessment branch gates passed |
| Compile, generated schemas, Ruff, mypy, assessment policy | Passed |
| Economic, DSH, job and provider-package compatibility | Passed |
| Node integration and three-domain stack demonstration | Passed |
| Strict router verifier | Core, OpenAI and marketplace contract passed; live marketplace disabled |
| Wheel and source archive | Built with existing dependencies, without isolation or installation |

Both pytest runs emitted one existing Starlette/httpx deprecation warning.
Skipped tests remain skipped; they are not evidence of live execution. The strict
router verifier's readiness result covers its existing contract, not the new
stack onboarding gate or comparative benefit.

[Final command records](final-checks-v3.json), [compatibility command records](compatibility-checks.json),
[coverage details](coverage-report.log), [package hashes](packaging-final.json)
and [machine-readable summary](summary.json) retain the exact results. Earlier
failed and interrupted logs remain alongside them. The active verification-lock
amendment is recorded in [its review](verification-lock-review.json); historical
qualification results and thresholds were not changed.

The first release remains incomplete. Existing Hugging Face and Figma access
checks and the pinned local Python check provide limited real connectivity
evidence. An operator-completed authentication handoff, a credential-bound free
billing/readiness check, and standalone integration evidence for the selected
providers remain open. See [the provider next steps](../stack-readiness/provider-next-steps.md).
No paid generation, credential extraction, installation or container operation
was performed. Paid remote execution and the controlled comparison remain later
milestones with their own authority and evidence requirements.

The final storage audit remained above the 50 GiB reserve; exact free bytes are
in the summary. Build outputs, test records and existing persistent resources
were retained. No cleanup or external publication was performed.
