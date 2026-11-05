# Official prebuilt environments for the six selected SkillsBench tasks

The [upstream v1.1 image map](https://github.com/benchflow-ai/skillsbench-leaderboard/blob/820ee3df9e7227b04f0c60ffe1415aad8a14eebc/prebuilt_images/skillsbench-v1.1.json)
contains all six selected tasks. The [registry audit](runtime-candidates.json)
verifies the exact indexes, runtime manifests and configs from public GHCR
metadata. Each candidate is Linux amd64. Each Dockerfile matches the pinned
9a1f4dd5 task file at both the leaderboard task-source and runtime-source refs.

The map offers a way to reuse prepared upstream dependencies in place of
mutable installation scripts. Image manifests and Dockerfile equality alone
leave embedded input equivalence, skill exclusion, platform conformance and
asset rights open. Verify actual image contents and retained source provenance
before making an execution review. The largest single compressed candidate
is approximately 1.09 GB. Size estimates exclude extracted layers.

For sales pivot, the pinned Dockerfile describes ABS data under CC BY 4.0.
The shipped PDF and workbook have derived-file metadata, with the PDF title
and author anonymous and the workbook creator openpyxl. The
[ABS copyright statement](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer)
excludes some material from its general license. Retain the task declaration
and establish the originating tables and attribution before any disclosure.

Only registry metadata was read. No image layer, dependency, task program,
verifier or model ran. Task pin and six-task scope remain intact.
