# Exact audit-correction execution review

Approval bundle SHA-256: `9aaa3f73aeca2692361428d1b8eada3a9b3ff7b5ad6018dcb06b7811a19f6f20`.

The first approved grader review stopped after one observation because its audit
expected container fields omitted from minimized receipts. The failed request and
its three charges remain. Its canonical attempt completed, and a read-only check
confirmed its exact owned container is absent. The corrected audit derives that
name from the canonical attempt and passes six regression checks. The receipt
privacy allowlist is unchanged.

The existing provider-layering failure is also corrected: core calls the host
registry, which delegates to the unchanged Codex envelope validator. No dependency,
collector, worker image, model, destination or scientific threshold changed.

| Component | Exact work | Permission bound |
| --- | --- | --- |
| Grader | Fresh request `recipe_generation_924370040ba64561b68940a8999f584f`; 23 offline container observations on fixed development cases | 25 existing-grant operations, at most 1240 reserved seconds; no model turns |
| Package | Wheel `11f798a762bdcdf7095164202d870822cc2374664764d508e4a25279087cae45` plus 32 exact cached dependencies; 18 sandboxed installed checks | Private environment; remove only unchanged owned runtime and scratch |
| Documentation | Cached Lychee 0.24.2; current 69 public documents | Offline sandbox; retain logs and remove its unchanged runtime |

Source digest: `5f4e318c7146419cf7c10f3c057e1b6fef6ea8fbc6f607e221759a67820ba9c6`. Code commit:
`6e3086898721b9f43e292b4791416ca476c89ffc`.
Both full runs passed 1623 tests, with 21 skips and one existing warning. Coverage
reports 82%; both branch gates and all 13 integrated checks pass. All nine
supplemental checks pass, including 13 Node tests. The actual built wheel's six
relevant modules match source; all 33 wheel hashes match. No installation or new
contained attempt has started.

No dependency download, image build/pull, model proxy, model call, credential
access, cash spending, host activation, publication or retained-resource cleanup.
The earlier three operation charges remain. Each new component has one attempt;
unstarted independent components remain covered if the dispatcher fails. Never
replay a started component or reuse the old request ID.

## Why approval is needed

The earlier bundle's grader attempt is terminal and binds the old runner/source.
The operator's pasted continuation excludes untrusted software execution and
requires current-source installation review; CONTINUATION.md also requires
applicable container-provisioning authority. This review binds the corrected
runner and wheel. Routine definition and finite scope amendments remain delegated.
No architecture decision or larger grant is requested.

## What remains separate

The fresh first-party management fixture passed admission/use, revocation, stale
rejection and baseline selection. That is synthetic lifecycle evidence. The
historical real comparison remains INCONCLUSIVE. The repository mapping draft is
inert; independent task cohorts and complete frozen four-arm and selection plans
remain unfinished. This bundle supplies neither live usefulness nor selection
value, resource acceptance, human-control completion or release authority.

After actual approval, save the verbatim answer and this raw bundle digest in
`bundle-operator-approval.json`, then run `run-bundle.py` with that digest. The
approval question alone is not an approval record.
