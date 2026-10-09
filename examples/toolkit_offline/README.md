# Offline evaluation fixtures

These three tasks test the evaluation workflow with scripted file edits. Both arms
have the same editing capability; treatment also receives the captured candidate.
No model interprets that candidate, and no benefit is inferred from these results.

The trivial edit repairs one word. The complex edit renames an interface across
two files while preserving a third file and unrelated comments. The adjacent
task preserves its input. Expected artifact digests were made from independent
literal results. They stay with the coordinator; workers receive only current
input files and requested changes.

The suite explicitly retains these public synthetic output files for verification.
General suites default to retaining no output contents. The nested
`resources/evals` sentinel tests exclusion from the deployed candidate payload.

## Run the reviewed fixture

Run from the repository root on the recorded macOS arm64 / Python 3.13 host.
Use an existing verified evaluator runtime and the pinned local Docker image.
These commands do not install packages, pull images, start a service or call a
model. The output directory must be new, with an existing parent.

```bash
AE_TOOLKIT_OPTIONS=(
  --candidate "$PWD/examples/toolkit_offline/format-json"
  --suite "$PWD/examples/toolkit_offline/suite.json"
  --source "$PWD/examples/toolkit_offline/source.json"
  --runtime /private/tmp/aeep-ase-c04-tt14mj6r/rebuild
  --output "$PWD/aeep-offline-result"
  --image sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7
  --docker /usr/local/bin/docker
  --socket /Users/edwintse/.docker/run/docker.sock
)
PYTHONPATH=src python3 -B integrations/toolkit/evaluate.py plan "${AE_TOOLKIT_OPTIONS[@]}"
```

The preview binds the captured candidate, suite, runtime inventory, adapter
sources, image and output destination. Review it, then pass its `review_sha256`
value to the run command:

```bash
PYTHONPATH=src python3 integrations/toolkit/evaluate.py run "${AE_TOOLKIT_OPTIONS[@]}"   --reviewed-digest REVIEW_SHA256_FROM_PLAN
PYTHONPATH=src python3 -B integrations/toolkit/evaluate.py report   --output "$PWD/aeep-offline-result"
```

Open `aeep-offline-result/report.html` or read `report.md`. The source-bound
[recorded transcript](../../reports/toolkit-v2/c06/offline-journey/commands.json)
contains the actual arguments and review used for the first replay.

The evaluator schedules six trials. AEEP reserves each operation before starting
its separate network-disabled worker. Treatment receives the exact candidate
files, including its resources; control receives none. Candidate instructions
are not interpreted or executed in this mode. The scripted worker edits the
current case's files, and the coordinator grades the returned artifact.

The [privacy replay](../../reports/toolkit-v2/c06/offline-journey/privacy-verification.json)
uses the same cases with `retain_outputs` omitted. It retains hashes, grades,
receipts and accounting without prompt, transcript or output contents. The report
then verifies canonical grading records; it cannot inspect discarded output bytes.
Keep the local receipt database for later verification. Sharing a report does
not require sharing that database.

Both arms passed all three recorded cases. The existing analysis returned
`insufficient_evidence`; the value verdict is `NOT_ASSESSED`. Model tokens,
model latency and actual cash remain unknown. Worker elapsed time is assessment
overhead. These fixtures do not establish candidate usefulness or live Codex
conformance.

For package setup and non-destructive removal, use the
[private installer guide](../../docs/aeep-toolkit/INSTALLATION_DESIGN.md#implemented-private-wheel-runtime).
The toolkit's `doctor --host codex --project /absolute/project` reads project
connection metadata; the development stack's `inventory --runtime /absolute/runtime`
checks the evaluator files without importing them. Neither substitutes for a
real host conformance test.

If a worker fails, dispatch stops and keeps the incurred or unresolved operation.
The partial report shows expected positions, receipts, unknown grades and missing
results. Run the same `report` command to verify those records. Do not replay into
that output directory or treat an unresolved operation as refunded allowance.
The partial report's worker-operation elapsed subtotal is assessment overhead;
model time and full evaluation cost remain separate unknowns.
