# Controlled engineering attempt stopped before models

Approved `b01793ac` ran once. The COPY-only image built successfully and remains
as `aeep-toolkit-v2/ase-stack-check:reviewed-20261103`, image
`sha256:10a756a7d47927399dce703cecb6a5d56706ddcbb158782ed11becca1492fd88`.
Paired readiness stopped at treatment identity/policy. Neither model plan ran;
model turns remain 3,796. The proxy is restored stopped, both newly owned worker
containers are removed, and the runtime/source are unchanged. Four operations
and 12.034440374 elapsed seconds remain charged. Old reservations are untouched.
The initial inspection setup-cost record remains explicit; no complete composed
accounting or infrastructure acceptance is claimed.

Read-only archive-header inspection of the three new COPY layers found mode
`0444` on `/opt/dependencies/aeep-stack-check`, `/etc/codex/skills` and
`/etc/codex/skills/aeep-stack-check`. Files correctly have `0444`, but nonroot
workers cannot traverse those directories. The first archive lookup used
uncompressed layer IDs and found no records; the second used the actual saved
manifest's layer paths. Both observations remain. No Linux program, diagnostic
container or authentication file was executed/read for that archive audit; no
image archive was retained.

The collector wrapper also discarded the treatment's partial observation after
its initial read failed. A corrected wrapper must return that observation before
attempting collector access. Static review additionally found that raw paired
inspection output is not a canonical readiness certificate: the existing explicit
conformance-assembly step was missing from the proposed engine driver. Fix that
handoff through the ordinary CLI and validate it before another attempt.

The original failed run and review remain immutable. A new bounded review must
cover the directory-only image correction and fresh containment. The two model
turns remain unstarted; retain the original cumulative 144-operation / 6,200-second
ceiling. No installation, new dependency, download or service/destination change
is proposed. All comparative, SkillsBench domain, usefulness, resource and release
gates stay open. No qualification, admission or savings claim follows.

Evidence: [execution result](execution-result.json),
[paired inspection](boundary-result.json), [built image](built-image.json),
[image directory modes](image-mode-audit-v2.json), and
[saved layer-path metadata](saved-image-manifest-metadata.json).
