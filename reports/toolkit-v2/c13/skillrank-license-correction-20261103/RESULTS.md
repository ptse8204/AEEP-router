# Pinned SkillRank build and registry lifecycle passed

Review `6057c786` completed the unstarted runtime phases. The unchanged SkillRank
source at `5216bae9149b4ff8a7f9e014b6889fb094cee8e1` built offline and its actual
upstream local registry served search/show requests. No model task ran.

| Check | Actual result |
| --- | --- |
|86 locked archive checksums and manifest license expressions | PASS; one archive reused,85 fetched |
| Offline source build | PASS; release build completed in26.86seconds |
| CLI/compiler identities | SkillRank0.1.5; Rust1.94.1 |
| Real upstream search/show | PASS against the reviewed first-party catalog |
| Missing record | Expected nonzero exit and explicit `not found` |
| Host-file/root-write/socket/external-network denial | PASS |
| Selected loopback and owned workspace access | PASS |
| New container cleanup | All three absent/removed by verified identity |

The [canonical result](runtime-execution/summary.json) binds the retained binary
`0996e6d80ad59046140f2763cf067e979941135a020a8489e0752d23653d8708`
to compiler image
`sha256:c596ad3e4f5fbe2498d6f71498349691b9ee219288e298ec78f1f3dcd41124e8`.
The actual vendor tree is
`0daffbb992a65dcc41807f56ae5595b2b4ed04f5d60f0c719319683103759f5b`.
All source/license files,archives,build output,image and runtime remain available.
The upstream local catalog's `safe` values remain provider claims,not scan evidence.

The original grant was reused. Its cumulative counters are **16operations,
zero model reservations and55.93853883491829grant seconds**, within40/0/4,500 and
zero cash authority. Old charges were not reset. The expiry-only amendment is
recorded; no new grant was created. Wrapper timing excludes nested operations;
Docker-client resources are not container resource measurements. No complete
resource-qualification or savings claim follows from these engineering timings.
Actual cash measurement remains unavailable.

The first coordinator launch found an absent task-owned parent before any new
operation was reserved. [The preparation amendment](preparation-history/parent-creation-amendment.json)
retains that failed start,creates only the expected private parent,and records
the unchanged counters and executable bytes. The still-unstarted approved phases
then ran under the standing preparation delegation. No upstream phase was replayed.

The [earlier corrected-wheel and docs results](../skillrank-build-preparation-20261103/RESULTS.md)
remain passed and were not repeated. Product source remains the checked e48eec5f
snapshot. All prior images,volumes,runtimes,backups and unrelated work stay.

This proves component build/search/show and the checked container lifecycle.
It does **not** close SkillRank's bounded evaluation callback or ordinary operator
workflow integration. The next implementation connects the retained executable
to selected setup/readiness/use/removal through existing Toolkit controls.
Both SkillsBench domains,remaining upstream integrations,candidate usefulness,
selection usefulness,resource qualification and release remain open. Comparisons
remain paused; Waza still lacks supported backend access.
