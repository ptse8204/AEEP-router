# Spreadsheets worker review

These are concrete local image definitions and diagnostic results, not approved
assessment environments. No model calls, authentication transfers or grant
amendments were made. The existing live allowance is unchanged.

| Arm | Immutable local image | Observed enabled skills |
| --- | --- | --- |
| Plain Codex | `sha256:c2dd47ee717cff588507a4c0adb3b4fe303e9397b0f8f53fa529139accc3a13d` | None |
| Spreadsheets workflow | `sha256:7424e9ed9ac41dc449a91a0ad773548295e6d601ea24ff81deca9846700dc613` | `spreadsheets:Spreadsheets` |

Both images use Codex 0.154.0, the same Node/Python bases, launcher,
configuration and filesystem permission profile. The candidate contains the
complete selected package snapshot and its Linux artifact-tool dependencies.
The local Spreadsheets skill is discovered through `/etc/codex/skills`;
the connected Excel skill is not registered. This is the proposed local-file
workflow comparison, not a claim about the connected Excel service.

The system skill exclusions use observed paths and TOML inline tables in CLI
overrides. The first diagnostic discovered six bundled system skills; all six
were subsequently reported disabled in both arms. The first override attempt
used JSON object syntax and was rejected before execution. Its separate record
is retained. Inventory enablement does not prove invocation restrictions.

The candidate launcher creates a private symlink to the immutable runtime at
the installed skill's documented fallback location. An actual sandboxed command
found Node and artifact-tool there, imported CSV and checked the resulting
values. The installed authoring helper also exited successfully. The plain arm
confirmed that the plugin and artifact-tool were absent. An initial diagnostic
script had a quoting error; that was a test defect, not a plugin failure.

The earlier dependency report said the authoring helper was missing. The current
38-file package snapshot contains it at
`skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs`.
`plugin-manifest.json` freezes every package file, including that helper. Earlier
reports retain their original observations; this review supersedes that missing
dependency claim for this exact snapshot.

## Evidence and reproduction

- [Candidate observations](../spreadsheets-worker-review.json) and
  [plain observations](../plain-worker-review.json) include image/worker
  bindings, actual inventory responses, command exit results and cleanup.
- `spreadsheets-context-manifest.json` and `plain-context-manifest.json` bind
  build inputs by file digest or symlink target. The local contexts are
  `/tmp/aeep-spreadsheets-worker-review` and `/tmp/aeep-plain-worker-review`.
  They contain no login state or campaign answers. Large installed dependencies
  and binaries are not copied into this repository.
- `Dockerfile`, `Dockerfile.plain`, `worker-launch`, `worker-config.json` and
  `requirements.toml` contain the exact review definitions. The two probe
  scripts reproduce the no-model observations using these local contexts.
- Run either script from the repository with `PYTHONPATH=src python3` only after
  checking the pinned image and context identities. These diagnostic scripts
  write reports; use new output names to retain earlier evidence.

The official [skill discovery documentation](https://learn.chatgpt.com/docs/build-skills)
describes the admin discovery path and symlink support. The installed version's
actual `skills/list` result is retained separately from that documentation.

## Remaining release gates

The review images have no network and no credentials. They cannot run the live
campaign. A final model-service egress policy, protected Codex-managed login,
post-login effective policy and identity checks, complete boundary probes, and
an amendment of the existing grant are still required. That amendment must bind
the final definitions and preserve the original counters. Do not turn these
diagnostic worker bindings into approvals or conformance records.

The candidate's draft `dependencies_digest` in the diagnostic worker identifies
the package manifest; the immutable image binds the complete runtime. A final
assessment binding must additionally reference the full reviewed dependency
manifest. The runtime check covers local CSV access and helper execution, not
every authoring feature or actual model-driven skill use. App Server remains
experimental. These results establish neither plugin savings nor release
readiness.
