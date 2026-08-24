# AEEP 0.5 deterministic economic-evidence proof

This campaign extends AEEP's benchmark evidence with the real prepared-routing path. The paid
trials call `Router.prepare_route()`, reserve the signed maximum, call
`Router.execute_prepared()`, verify provider usage, settle the measured charge, and release the
remainder. It uses only the in-process reference provider, deterministic test keys, a local
prepaid ledger, and synthetic text. It does not need external credentials or persist action
payloads.

Run the measured campaign from the repository root:

```bash
PYTHONPATH=src python examples/economic_evidence/campaign.py --repetitions 30
```

Validate the checked, sanitized artifacts without rerunning transports:

```bash
PYTHONPATH=src python examples/economic_evidence/campaign.py \
  --repetitions 30 --check --require-gates
```

`--require-gates` makes the command fail when a required economic gate, including the measured
settlement-oracle gate, is unmet. Evidence-safety violations fail even without that flag. The
time and token engineering targets remain explicit report results; they are not silently turned
into release-gate passes.

The checked run contains 420 trials: seven route types, 30 repetitions, process-cold and
router-warm conditions, and equal qualification/training/holdout splits. The route types are
local Python, local CLI, direct HTTP mock transport, local MCP stdio, a usage-priced provider,
an unknown-cash subscription baseline, and the AEEP hybrid decision. HTTP stays in-process; MCP
and CLI processes use exact argv arrays. Subscription token counts are synthetic and visibly
flagged, so they are excluded from token-saving claims. The hybrid router learned from 40 real
qualification/training observations; the oracle is evaluated only on the 20 held-out
condition/repetition cases. A separate two-step prepared workflow trial is reported outside the
420 single-action trials.

## Measured result

- All 420/420 executions produced the task-valid deterministic result.
- All 66 paid executions retained a signed quote and payment-settlement evidence.
- Each paid trial quoted USD 0.0040 expected and USD 0.0050 maximum, reserved USD 0.0050,
  captured USD 0.0038, and released USD 0.0012.
- There were zero overcapture, quote-failure, settlement-failure, or indeterminate incidents.
- All 180 unknown-cash trials remained unknown; none was reported as USD 0.
- After the 40 qualification/training observations, the hybrid route was within 10% of the
  cheapest successful authoritatively costed route in 20/20 held-out cases.
- The two-step prepared workflow proof passed 1/1: both real dependency inputs were bound before
  preparation, and its paid step retained quote, reservation, settlement, capture, and release
  evidence.
- The hybrid median total time was 12.301000 ms versus 0.0326665 ms for the fastest measured
  baseline, so the 15% time-reduction target failed. No timing improvement is claimed.
- The two-domain 20% model-token target was not evaluated: this local campaign has one domain
  and no complete live subscription-model usage evidence.

See [report.json](report.json) for exact per-trial evidence and [report.md](report.md) for the
human-readable proof. IDs in those artifacts are deterministic pseudonyms; raw input and random
runtime identifiers are not included.
