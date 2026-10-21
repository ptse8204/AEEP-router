# Recommended production workload and resource budgets

Run the first production target on this Mac as a single-user Python CLI with
local receipts and private HTML/Markdown reports. Keep assessment containers on
demand, one campaign at a time. This uses the stack already built: agent-skill-eval
for its tested scripted path, the existing AEEP managed fallback for Codex, and
existing instrumentation. No hosted database, orchestrator or new framework is
needed. These are proposed targets, not passed measurements or execution authority.

## Workload to qualify

Plan for up to 50 local intake, preview and report operations per working day.
This is a capacity recommendation, not an observation of your use. Keep the
existing candidate limits: 512 regular files, 8 MiB total, 1 MiB per file and
1,024 tree entries. The normalized local report profile covers at most 200 run
records and 1 MiB of JSON. Larger canonical managed campaigns remain separate;
they must not be truncated to fit this profile.

A manually reviewed assessment uses distinct baseline/treatment worker profiles,
with one model task executing at a time. Its exact candidate, model, fixtures,
permissions and allowance still need their existing review. Automatic admission,
arbitrary repository debugging and broader platforms are outside this first
resource qualification. Normal CLI operation must work without those workers.

## Proposed acceptance targets

| Resource | Local CLI | Assessment mode |
|---|---|---|
| Response time | Candidate/preview p95 ≤1 s, maximum 3 s; report p95 ≤2 s, maximum 5 s | Current diagnostic-profile task cap ≤102 s; resource-only batch ≤60 minutes |
| Process memory | Peak CLI RSS ≤256 MiB | Coordinator ≤256 MiB RSS; retain worker 1,024 MB setting and proxy 512 MiB/no-swap setting |
| CPU | ≤1 CPU-second per candidate/preview; ≤2 per report | Mean whole-host increase ≤2 logical CPU cores over baseline |
| Whole-host memory | Record before/during/after; no background Toolkit service | Increase ≤4 GiB; require ≥6 GiB available before start and ≥2 GiB during operation |
| Network | Denied for local core commands | Existing reviewed model destination only; ≤256 MiB total worker RX+TX for the 12-turn resource batch, proxy traffic recorded separately |
| Idle operation | No owned child/listener remaining after 60 s | Workers removed and reviewed proxy restored stopped; unrelated Docker processes preserved |
| Storage | Private installed runtime ≤512 MiB | New evidence ≤1 GiB per campaign, scratch ≤2 GiB; review new retained evidence at 10 GiB |
| Free disk | Require 55 GiB before new setup/assessment and preserve 50 GiB throughout | Same reserve; no automatic purge |
| Cash | No paid service | $0 authorized cash; subscription billing/usage remains separately reported or unknown |

The earlier calibration observed roughly 43 MiB sampled CLI memory and 0.13–0.14 s
median command time on a smaller source-checkout workload. The proposed limits
leave room for larger inputs and packaging overhead. Those measurements do not
prove the targets. The current Mac has 24 GiB RAM; the earlier calibration had
about 5.1 GiB available. A fresh start check may therefore require you to close
other applications before an assessment. We will not close them automatically.

Most entries are acceptance targets, not existing runtime enforcement. The worker
and proxy settings are preserved existing controls. A future reviewed runner must
observe and apply the declared stop rules. Missing peak/host/network measurements
cannot be relabeled as passing.

## One bounded qualification, then a decision

First accept the targets. Then freeze fresh inputs, exact artifact/runtime/driver
pins, order, verifiers and resource definitions before execution. Do not reuse the
24-command calibration as held-out evidence or choose passing limits afterward.

1. Run 30 new local transactions: 10 candidate inspections, 10 previews and 10
   report renders. Add two counted warm-ups per class and at most six rejection
   checks, for at most 42 CLI invocations and zero models. Use three rounds, each
   with 60-second whole-host baselines before and after. Report nearest-rank p95
   per class and all individual values; ten samples do not establish population
   tail latency.
2. If core checks pass and exact execution authority is available, run at most
   12 resource-only model turns: six new public editing cases, two per bounded
   family, once in each arm. One model task at a time, no automatic retries,
   at most 500 operations, 12,000 charged operation-seconds and 3,600 elapsed
   seconds. These are distinct ceilings because operation intervals can overlap.
   This is not a new value study, qualification or admission. Do not replay the
   original 564-task campaign.
3. Compare results with the frozen targets. Stop on a breach or missing evidence;
   retain the result and costs. A passing local result covers this declared local
   envelope only. Production/release decisions still use the other C13 gates.

The 12-turn allowance and any fresh private installation are proposals, not
approved execution. The preceding five diagnostic reservations are terminal.
A separate exact review must bind any future live batch and installed-wheel
check. A full future value study would still need its existing screening/training/
100-plus-holdout requirements; these 12 turns cannot replace them.

## Measure the whole stack accurately

Keep host CPU, available memory, swap and network baselines alongside owned-process
and container counters. Prime nonblocking CPU counters and discard their first
value, as described in the [psutil documentation](https://psutil.readthedocs.io/stable/index.html).
The installed psutil 6.1.1 is unchanged. Use CPU-time deltas where available and
retain sampling limits; sampled RSS alone cannot certify a hard peak ceiling.

Keep raw usage/cache fields from Docker. The [Docker stats reference](https://docs.docker.com/reference/cli/docker/container/stats/)
explains that the Linux CLI subtracts cache from displayed memory. Include Docker
VM overhead in host measurements and keep it separate from container RSS, so
memory is not counted twice. Record warm/cold VM state separately because
[Resource Saver](https://docs.docker.com/desktop/use-desktop/resource-saver/)
can stop the VM. Do not change global Docker settings for this test.

A baseline with mean CPU over 0.25 logical cores, or a before/after available-memory
median shift over 512 MiB, does not support an attributable whole-host pass.
Preserve a contaminated run and costs; no automatic repeat. Energy remains
unknown without separately reviewed measurement. This proposal makes no energy,
battery, provider-metering or monetary-savings claim.

The [machine-readable proposal](production-resource-proposal.json) records exact
units, caps, source/wheel pins, stop rules and remaining authority. Your immediate
control exercise is in [CONTROL_CHECK.md](CONTROL_CHECK.md).
