# AEEP v0.5 live DeepSeek Harness proof

Status: **passed** on 2026-08-24 with synthetic data only.

The bounded proof ran six user turns in DeepSeek Harness `0.1.0-rc.7` using `deepseek-v4-flash`. Every turn made exactly one resolved AEEP tool call. The run produced the expected three AEEP execution receipts: one deterministic `text.stats` receipt and two `dsh.coding-tools.read-file@1` receipts.

The two reads ran in different Harness sessions and produced the same sanitized semantic digest, `sha256:f7881fd4df3425ff5bf14d0b7bdb9b6ce1f0cea888d8162c8ee8646bdc76f2fb`. The digest covers only `{"ok":true,"path":"document.txt"}`; fixture content is deliberately excluded.

The final turn requested the inactive `dsh.coding-tools.apply-patch@1` capability. AEEP returned `NoRouteError` before provider execution, no execution receipt was created, and `should-not-exist.txt` does not exist.

## Safety evidence

- Workspace: separate `AEEP-dsh-test` directory, mode `0555`.
- Fixture: `document.txt`, mode `0444`.
- Fixture digest before and after: `sha256:9b3f1fb1fbf770f73e6fe5ae4faa4110671a6c66f7a7cdf7623357dca062c990`.
- Qualification executions: 1 cold execution, below the maximum of 2.
- Active community routes during proof: 1.
- Active community routes after proof: 0; all 18 imported candidates are suspended.
- Synthetic sentinel matches in AEEP SQLite persistence: 0.
- DSH verification receipts: 6 distinct hashes, each with one top-level call, no nested calls, and no unresolved calls.

## Measured DSH usage

| Metric | Value |
|---|---:|
| Model calls | 12 |
| Input tokens | 20,514 |
| Output tokens | 920 |
| Cache-read tokens | 127,488 |
| Cache-write tokens | 0 |
| Provider-reported total | 148,922 |

The total is the sum of the provider-reported token buckets. It is reported as DSH evidence only and was not imported into AEEP's economic observations, estimator, or cash accounting.

DeepSeek Harness remains running at `http://127.0.0.1:3080/` as requested. The temporary community route is suspended, so leaving the Harness process up does not leave that route active.
