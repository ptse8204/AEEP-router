# Connect the upstream scheduler to canonical evaluation

Workflow v2 can now select the ASE scheduling adapter without changing the
selected managed fallback. Setup v3 and plan v8 bind a reviewed scheduler,
complete retained runtime, exact command/profile and the 16 pinned upstream
source files. Historical setups/plans keep their serialized meaning. A missing
or changed scheduler stops before job claim; no fallback is inferred.

The existing BenchmarkRunner has a bounded scheduling port. It preserves the
canonical trial order, durable claims, worker checks, execution, protected task
grading, receipts and recovery. Omitted, repeated or reordered requests stop the
run. Only one to six required-use qualification cases with fresh trial conditions
are supported. Formal qualification and value campaigns remain unavailable.

The new child uses the actual upstream AgentHarness base and EvalRunner APIs.
It never calls FakeHarness. Its opaque slots request canonical parent trials.
The upstream deterministic JSON assertion checks the canonical protected-grade
certificate; it is not an independent second task verifier. Native upstream
Codex launch/parsing remain unsupported. All upstream token/time defaults stay
compatibility artifacts and are excluded from AEEP measurements. Historical
FakeHarness examples and results remain unchanged and retain their old scope.

A scheduler operation is reserved in the existing grant before workspace setup.
The child has no control database or grant. SDK overhead excludes every awaited
canonical trial interval, including its router setup and protected grading.
The existing trial and grader charges remain. Full surrounding workflow
inspection/preparation/export accounting is still unfinished; this is not a
claim of complete composed cost coverage.

The new CLI command stores an inert scheduling definition; it cannot review it:

```bash
PYTHONPATH=src python3 -m aeep_toolkit workflow define-scheduler \
  --file /absolute/path/scheduler.json --manifest /absolute/path/manifest.json
```

A selected v2 workflow binds that file under `scheduler`. Its setup-v3 request
and canonical plan-v8 must reference the same definition. Execution still
requires current reviews, grant, worker conformance and exact bounded engineering
authority. A catalog or prepared definition does not supply those permissions.

Focused source verification passed 112 tests; the scheduler/child subset passed
24. These use labeled first-party SDK substitutes and existing first-party
execution. No actual optional SDK was imported or run. All 13 source checks passed
on unchanged source a762c5f0e9ce0279d18a873b8289a34308482fbbc4ea0492cb5db68623bdab96;
Both full runs passed 1,930 tests and skipped 21, with 82% combined coverage,
both branch gates and a successful build. See the actual
[check record](verification/checks.json).
The working digest includes preserved unrelated CI changes, which must be
excluded from this implementation commit. No model, Docker mutation, service,
credential access, activation, publication or release occurred.

The [database manifest](dependency-audit-db-metadata.json) resolves the external
Trivy database used by the selected dependency-audit task to dataset revision
d005409588e3f74449ab3f13cde29cfea87a80bc, archive84,027,328 bytes, SHA-256
e67dd9144e93897c5e2dbe4228e3444e4818130923e39389f32164a01bb62d0f.
That revision has no license/readme; use rights remain unresolved. Only public
metadata was read. The database was not downloaded or executed. Existing six-task
assets contain no Git LFS pointer substitutions. Immutable runtime dependencies,
asset rights, original verifier reference/counterexample runs and both full domain
journeys remain open. The all-integration gate is not passed; comparisons stay
paused. Pending shared SDK review fb7fc581 retains its frozen0cb8f956 scope and
has not been executed or silently enlarged for these new source changes.

The current-input offline documentation review is prepared and unexecuted:
[operation-review.json](docs-review/operation-review.json), SHA-256
cf63f3e642bf6630c682dd553e55558ebd31ce3bdcc5c5681b17c1fe81b97761.
It binds the cached tools and 72 inputs, permits at most three Markdown-only
correction attempts, and retains its owned reusable runtime. Six standard-library
boundary probes passed. No Node, Lychee or other upstream tool ran in preparation.
