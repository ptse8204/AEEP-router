# Controlled evaluator correction and ordinary readiness

The ordinary workflow CLI now prepares canonical readiness from settled paired
inspections. It reuses the existing worker, probe, journal, accounting, conformance
and review contracts. Existing v1/v2 workflow definitions keep their meanings.

`workflow prepare-worker-readiness` verifies the two request IDs, all eleven
probe identities per worker, terminal journals, current source, worker identity
and settled same-grant charges. Selected collectors require a denial observation
in the same journal. It stores unreviewed definitions and an amendment proposal;
existing operator review and conformance checks still control consumption. It
starts no worker, grants no authority and never replays an inspection.

All thirteen [source checks](verification/checks.json) pass on
`c48e931b47647a400d87f7e1236821ff4243c2ca20f2d6f1dd8f5e4ec5d10659`.
Both full test runs passed 2,041 tests, with 21 intentional skips. Total combined
coverage is 82.62%; both required branch gates pass. The installed wheel check is
prepared, not executed. The [source inventory](source-snapshot.json) preserves the
exact tested checkout in a private local snapshot, including unrelated CI edits
that remain outside these feature commits. The source digest describes those
bytes; it is not a claim that the feature commit includes someone else's edits. Twenty focused readiness tests use temporary synthetic
state and do not establish actual worker conformance.

The approved `b01793ac` attempt retained image `10a756a7d479`, then stopped at
worker readiness before models. Its [results](../ase-controlled-workflow-20261103/RESULTS.md)
retain four operations and zero model turns. COPY set required directories to
0444. Further static inspection found that Codex needs the existing directory-
symlink alias pattern and rejects the fixture's recursive `aeep-` name.

The correction uses the retained original control image, explicit 0555 directory
modes, 0444 files and a directory symlink. It pins the renamed `stack-check`
fixture at commit `f8f9fba391f32942ebc2471b702c95df936313e7`; the recursion guard
stays unchanged. No corrected image has been built. First-party
[packaging controls](packaging-controls.json) verify constructor, catalog mapping,
recursion rejection and alias behavior; actual Codex inventory is still unobserved.

The proposed run verifies the new layers before fresh workers, preserves partial
inspection failures, and uses the ordinary readiness command before preparing
one ASE and one explicitly selected managed-engine task. Both are required-use
engineering checks on the same previously exposed public task. They are not a
capability comparison, a SkillsBench journey or qualification evidence.

The original cumulative ceiling remains 144 operations, 6,200 reserved seconds,
two model turns and zero cash. The four charged operations remain inside it.
The measured historical static inspection is reconciled once under its original
scope; no duration is inferred or refunded. Canonical execution and setup
intervals are excluded from wrapper timing to avoid double counting. Complete
product-wide workflow accounting remains a separate open gate.

One grouped review also binds the current wheel with 32 unchanged cached
dependencies and the 72 current documentation inputs with retained offline tools.
Components have separate attempts. No downloads, pulls, new destinations,
credentials, admission or release are proposed. All images, runtimes, volumes,
backups and unrelated work stay. The proxy must return to its original stopped
state. Keep the normal 50 GiB actual-free-space reserve.

Next: obtain applicable approval for this changed image/candidate, fresh worker
attempt and changed installed artifact. Then run each component once under that
review and inspect canonical evidence before continuing. Do not replay terminal
attempts or transfer older source evidence. Comparisons stay paused; all-stack,
both-domain, usefulness, resource and release acceptance remain open.
