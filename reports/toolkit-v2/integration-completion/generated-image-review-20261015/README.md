# Older generated-tool Docker image review

Review date: October 15, 2026. Identification only; no Docker resources changed.

Of the 22 historical images, 18 are eligible for removal without affecting the
two audited remaining V2 plans or existing containers. Preserve the four CSV
images linked to an interrupted historical assessment. This review does not
authorize removal and does not classify other Docker objects.

## Space estimate

The 18 candidates total **19,126,121,954 bytes (19.13 GB)** in Docker's displayed
image sizes, but only **1,422,061 bytes (1.42 MB; 1.36 MiB)** are reported
as unique to them. Shared base layers remain needed by retained images. Removing
these candidates will not provide the gigabytes needed to reach 70 GiB free.

A separate layer check found 35 exclusive unpacked chains, with 757,760 bytes
reported in image history. No additional chains are shared only among the
candidate images. These layer bytes overlap the unique-size accounting; do not
add them to the 1,422,061-byte figure. Four initial multi-platform inspection
failures were resolved with eight explicit platform inspections; none shared
the candidates' added layers.

**Actual host-space recovery is unknown.** No deletion was performed. Build cache
and APFS snapshots can retain storage, so the host gain could be smaller or zero.
The estimate is Docker accounting, not a measured change in free host space.
See Docker's [shared and unique size definitions](https://github.com/docker/cli/blob/master/docs/reference/commandline/system_df.md).

## Exact decisions

Each row lists a historical build pair. The JSON review contains full IDs and
per-image byte counts. These 22 images currently have no tags and no container
references. Full IDs below identify the objects; no removal commands are supplied.

| Historical build pair | Decision | Image IDs (short) | Combined unique bytes |
|---|---|---|---:|
| Text schema local final | Removal candidate | `73b567b32f8f` / `29403c1c8f21` | 171,506 |
| Search recovery final | Removal candidate | `dfc681dacb67` / `bf4e035504f4` | 173,342 |
| Text phase final | Removal candidate | `7b28beeaf459` / `4778f6679a8f` | 172,079 |
| Workbook phase final | Removal candidate | `42c4eb7a973a` / `ea7683ba073f` | 108,713 |
| CSV phase final | Keep | `73445c9a5923` / `21dd54bfcc5f` | 118,531 |
| Search contract local final | Removal candidate | `0f9bc4304e1d` / `5241ac0258e6` | 173,388 |
| CSV schema local final | Keep | `6482627dbe8a` / `fef11d5e2cc1` | 118,518 |
| Workbook recovery final | Removal candidate | `1684f3ceb3e4` / `92385a9ac574` | 150,922 |
| Text recovery final | Removal candidate | `9ccb24e9a686` / `5059fe77001b` | 171,434 |
| Search phase final | Removal candidate | `f53a08ff7e6b` / `6542abd5ae62` | 181,930 |
| CSV recovery final | Removal candidate | `ac89db2bacfb` / `c9f4eda21a69` | 118,747 |

### Full image identities

#### Text schema local final — removal candidates

- `sha256:73b567b32f8ff37a9dd18ade141724a05b3ca3a1f1b0881ccfc47d292511b656`
- `sha256:29403c1c8f215cf935f6875c26a54b1621568446bc332fb9702f898b626bddd1`

Build evidence: [text-reusable-schema-local-final-image-result.json](../../../v08/text-reusable-schema-local-final-image-result.json).

#### Search recovery final — removal candidates

- `sha256:dfc681dacb6776f2079ed589d328583e34966c5ac2720537bc5b93d722ea1cbb`
- `sha256:bf4e035504f47ea637e7b20909232fdaf1f1967abcb14dbf0a91a03a385b799f`

Build evidence: [search-reusable-recovery-final-image-result.json](../../../v08/search-reusable-recovery-final-image-result.json).

#### Text phase final — removal candidates

- `sha256:7b28beeaf459e7d91caf88dbe0e6237fcbad2d66efb6213bb3be3a5beb1e95d7`
- `sha256:4778f6679a8f892d5606932149f92504d386e755636419e648bcf35a76db80af`

Build evidence: [text-reusable-phase-final-image-result.json](../../../v08/text-reusable-phase-final-image-result.json).

#### Workbook phase final — removal candidates

- `sha256:42c4eb7a973af98d0cc1a4bd4fb7e95036e699aa8f60c403e187396313ebc4fb`
- `sha256:ea7683ba073f9f2fe1b9e7b3aafa3917fea7caa02363495e3312538b7a7e6414`

Build evidence: [reusable-phase-final-image-readable-result.json](../../../v08/reusable-phase-final-image-readable-result.json).

#### CSV phase final — keep

- `sha256:73445c9a5923eef8879d079b3ed2b2ee5aec1770548525b41726e726eca7592f`
- `sha256:21dd54bfcc5f91cdc5597e2b5d07d3516df8318f3048b7612ec1b4dba5adc0bb`

Build evidence: [csv-reusable-phase-final-image-result.json](../../../v08/csv-reusable-phase-final-image-result.json).

#### Search contract local final — removal candidates

- `sha256:0f9bc4304e1d0f1864030a5b608b261d42a676856edb437dd2d6624045e36535`
- `sha256:5241ac0258e601e2a637358b1b15d204777088e21417580a224a3d57db4d7e9b`

Build evidence: [search-reusable-contract-local-final-image-result.json](../../../v08/search-reusable-contract-local-final-image-result.json).

#### CSV schema local final — keep

- `sha256:6482627dbe8a20a792d3f44b2166610e4ec2c81b430f3aba80f56d520021e5e5`
- `sha256:fef11d5e2cc12744db4b5f58c2dffae52793968c72b426a058aa6cb843183390`

Build evidence: [csv-reusable-schema-local-final-image-result.json](../../../v08/csv-reusable-schema-local-final-image-result.json).

#### Workbook recovery final — removal candidates

- `sha256:1684f3ceb3e4f102f35fe0af275c6ec751b500ac577d76ce43ad25a144101019`
- `sha256:92385a9ac574401ea3e0c05b08b26bdd4b6735744288001c6fe080ab4134f4d6`

Build evidence: [reusable-recovery-final-image-readable-result.json](../../../v08/reusable-recovery-final-image-readable-result.json).

#### Text recovery final — removal candidates

- `sha256:9ccb24e9a686cd7d4376cf04aee9c380a3f36046d6fe1992dc370f9ad9c340f1`
- `sha256:5059fe77001b46a1c08bd5bea61637c4338f5ac80c6b92676702190375d1f14e`

Build evidence: [text-reusable-recovery-final-image-result.json](../../../v08/text-reusable-recovery-final-image-result.json).

#### Search phase final — removal candidates

- `sha256:f53a08ff7e6bfdf1e84de097999ed70254830254231c3154d8e4a051f41a5eb9`
- `sha256:6542abd5ae627c657a782aa121dd83e4272de07fdb5a68c243b32454f13a6140`

Build evidence: [search-reusable-phase-final-image-result.json](../../../v08/search-reusable-phase-final-image-result.json).

#### CSV recovery final — removal candidates

- `sha256:ac89db2bacfbd05b878a0227a890e40755a69131047feec5a9ec144ba5fa8f86`
- `sha256:c9f4eda21a69c9ec0cf119c24a2a06691590916501cd8c91a901178daf5a3317`

Build evidence: [csv-reusable-recovery-final-image-result.json](../../../v08/csv-reusable-recovery-final-image-result.json).

## Why these decisions are bounded

- Both pending V2 plan dependency closures contain none of these 22 images:
  `plan_35da27e6045a4b5ebe38f7702ee46131` (generated-tool training) and
  `plan_0a8359a155184098ad3ba790f8a77f55` (editing qualification).
- All 13 containers, including stopped containers, were checked; none references
  any of the 22 images. Docker disk-usage data also reports zero references.
- Keep both CSV schema-local-final and phase-final pairs because their image
  definitions occur in the dependency closure of
  `plan_e915d9d5be214924859f7579a8bca5f0`. Its job
  `assessment_12735a46eb364c9c9cd2aa4868f290e1` is indeterminate after interruption.
  Preserve these recovery resources until that outcome is reconciled.
- Canonical generated-source hashes match retained build-output records for all
  22 images. Build results and historical receipts remain preserved. Removing the
  18 candidates would remove immediately runnable historical copies; a rebuild
  is not guaranteed to reproduce the same image digest.
- Current V2 control/treatment/runtime/proxy images, retained base images, volumes,
  build cache, backups and unknown resources are outside this removal scope.
- If removal is later requested, recheck exact image identities, every container
  and pending/recovery plan references before acting. No blanket pruning or
  forced removal is proposed.

## Retained evidence

- [Exact decisions and byte accounting](review.json)
- [Plan dependency and interrupted-job audit](dependency-audit.json)
- [All-container reference inventory](container-references.json)
- [Generated-source retention verification](source-retention.json)
- [Image-layer analysis](layer-analysis.json)
- [Resolution of multi-platform inspection failures](platform-inspection.json)

The dependency audit follows runtime definition, mapping, environment and
executable references in the canonical record store. Historical authority and
budget documents are not treated as runtime dependencies. It does not replace
fresh checks at a later removal time. No assessment state was changed.
