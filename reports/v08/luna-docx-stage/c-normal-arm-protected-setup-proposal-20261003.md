# Conditional normal-arm setup proposal

**Status:** preparation only; no image, worker, credential store, grant, or campaign was changed. Start only after the current C qualification is terminal and passes with source unchanged, cleanup confirmed, and its costs settled. Keep its evidence and holdouts intact.

## Image and worker profile

Reuse the existing plain Codex worker image as the normal-arm candidate: `sha256:85fa95d74a3124ea35015e747645fe85be03277bee04598675928a822987532d` (`aeep-sol61-successor-control:1592`, `linux/arm64`). The read-only image inspection recorded that exact image present, and the image plan describes it as the plain common base without the Spreadsheets treatment profile. It already includes the common `pandas==2.3.2` and `openpyxl==3.1.5` packages. The paired discovery and AEEP arms currently share `sha256:af37cdb28b380f9a01d16af4853680860f3c5a7c84f972e8f9d36dc53ac87e53` and the pinned physical skill at `/opt/dependencies/plugin/skills/spreadsheets/SKILL.md` (`fa24f7bd…82acc3f5`). The intended inventory delta is therefore just `skill:spreadsheets:Spreadsheets`; retain the shared `spreadsheets_bundle` inventory and the same fixed helper, ordinary tools, prompt, and task behavior across roles.

Do not build a new layer if a post-campaign, separately reserved metadata preflight confirms the plain image ID and the zero-turn normal-worker inspection confirms matching Codex/App Server runtime, Luna/xhigh support, common packages, and absence of the plugin skill/catalog entry. The earlier image inspection established ID/tag presence only, not current availability or runtime contents. If the ID is absent or those checks disagree, stop and prepare a separate pinned image request; do not pull, retag, or silently substitute the discovery/AEEP image.

Create a new normal executor and worker identity, with a fresh credential volume distinct from both `aeep-auth-incremental-control` and `aeep-auth-incremental-treatment`. Match the current profile's `codex-app-server` adapter, `gpt-6-luna`, `xhigh`, proxy `http://172.18.0.2:3128`, and private worker network `8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6`. The old normal profile is stale: it pins `gpt-6.1-sol`/medium, so reuse its image identity only, not its model configuration. Copy the discovery/fixed-helper configuration and remove only the Spreadsheets skill support from normal's effective inventory. Normal must have no AEEP candidate dynamic tool. Discovery and AEEP keep identical physical skill support; AEEP alone carries the optional candidate callback during value trials.

## Bounded setup after the gate

Reserve these proposed same-grant setup operations before each action; every one uses zero model turns and `$0` cash:

| Operation | Maximum | Purpose |
|---|---:|---|
| Host/Docker metadata and exact-image preflight | 1 op / 30 s | Check ordinary free space, Docker usage, image ID and proxy/network metadata; preserve the 50 GiB host reserve. |
| Fresh normal worker definition and zero-turn component inspection | 1 op / 600 s | Bind the exact image, common inventory, unique worker ID and new credential-volume name; verify model/runtime, skill absence and worker boundary. |
| Protected device sign-in | 1 op / 330 s | Operator runs the reviewed sign-in request in their own terminal. |
| Post-login normal-worker inspection | 1 op / 120 s | Verify the effective identity, model and managed permissions without returning raw config or authentication state. |

The proposed setup ceiling is **4 operations, 0 model turns, 1,080 seconds, $0**. The 600-second worker operation reuses an image; it is not a Docker build allowance. Any additional probes or changes need their own exact finite review. Preserve failed attempts and measured costs; do not reset the onboarding grant.

After a fresh normal bootstrap request is reviewed, the protected sign-in command is the policy-prescribed operator-terminal form:

```text
aeep assess --manifest MANIFEST signin-worker REQUEST
```

Replace `MANIFEST` and `REQUEST` only with the exact reviewed local paths/ID. The operator runs it directly; no agent output capture, login-code sharing, or authentication-state inspection. The exact normal request does not exist yet, so this proposal does not supply invented arguments.

## Conformance and value gate

The normal worker must pass fresh source-bound boundary and effective-inventory checks. Assemble a new three-role access definition and differential conformance: check every pair of worker IDs and credential volumes; discovery/AEEP retain the same physical skill, normal omits exactly that skill, and the candidate dynamic callback is absent from normal and discovery. Retain prior C worker evidence only if the current applicability validator proves its exact source and binding; never relabel two-role conformance as three-role evidence.

The current C profile is qualification exposure (`required`). It cannot be used as the AEEP value profile. The value profile needs a fresh AEEP successor with candidate exposure **optional**, fresh exact conformance for that profile, and a separately reviewed `aeep_value` plan. Require a passing canonical qualification job and independent grader before proposing the value stage, keep holdouts disjoint from qualification, and preserve the frozen task, model, prompt, utility dimensions, guardrails, and thresholds. No value calls begin from this setup proposal.

## Evidence pins

- Current C profile: `reports/v08/luna-docx-stage/c-current-profile-v1.json`, SHA-256 `8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449`; source `50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7`.
- Existing image metadata: `reports/v08/luna-docx-stage/b-existing-image-inspection.json`, SHA-256 `7893ab3efe6e241f0753bc4edd7a6b13fbd766a0e12c4d770580eef370f8683b` (read-only ID/tag observation; not conformance).
- Image/package plan: `reports/v08/luna-docx-stage/image-build-plan.json`, SHA-256 `e8690e0d56606ec6844cc1d93137e9511130b55633fb6814515bbcdf56ba3906` (plan identifies the plain 85fa base and common packages; it is not proof of current daemon state).
- Three-way policy: `docs/ASSESSMENT_TESTING.md`, especially “Original three-way AEEP-value experiment” and “Protected worker sign-in.”

This remains a conditional setup proposal. It is not a sign-in, scope approval, conformance pass, qualification, value-trial approval, or image-build authorization.
