# Current local CLI resource measurements

Twenty-four network-denied source-checkout commands completed on this Mac. They inspected inert synthetic metadata, listed Essentials, and rendered an existing synthetic report. No candidate code, evaluator worker, model, new package or service ran. The private scratch was removed after its immutable inputs and exact file set matched.

| Command | Samples | Median wall seconds | Maximum wall seconds | Maximum sampled RSS MiB |
|---|---:|---:|---:|---:|
| candidate | 8 | 0.143 | 0.151 | 42.66 |
| list | 8 | 0.129 | 0.133 | 40.92 |
| report | 8 | 0.132 | 0.143 | 42.14 |

| Shared-host phase | Samples | Median CPU percent | Minimum available memory GiB | Minimum disk free GiB |
|---|---:|---:|---:|---:|
| before | 50 | 0.00 | 5.13 | 141.65 |
| cli | 24 | 20.10 | 5.14 | 141.65 |
| after | 50 | 14.25 | 5.11 | 141.57 |

These shared-host observations include the profiler and unrelated work. Before/after differences cannot be attributed to the CLI. The child alone had network denied; aggregate host network counters are retained without claiming that traffic belongs to this task.

Process sampling reuses the existing AEEP monitor and can miss short children or peaks. CPU is a sampled lower bound and resident sums can include shared pages. Kernel cumulative child ru_maxrss remains raw in its native platform units. These are Framework Python/source-checkout measurements, not an installed-wheel memory claim.

This adds measured overhead to the older artifact-size inventory. It does not pass the production resource gate: no production workload, accepted resource ceilings or held-out resource trial was defined for this characterization. Whole Codex/assessment usage, energy and long-term retention growth remain unknown. No savings or billing amount is inferred.

The operation reserved 26 bounded slots for 24 commands and two baseline windows, on the existing grant with zero model allowance. All reservations/costs remain. Full samples, aggregate counters, environment versions, hashes and limits are in result.json; this summary is derived from that exact file.
