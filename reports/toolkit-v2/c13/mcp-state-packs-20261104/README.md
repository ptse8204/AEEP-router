# Represent the MCP tasks' actual database outputs

The selected PostgreSQL audit tasks require two database tables. A file-output
manifest would change their completion contract. This increment adds the separate
`aeep.toolkit.mcp-state-pack.v1` model and ordinary CLI inspection for those outputs.
Existing file-pack v1 models and serialization remain unchanged.

The state model binds an opaque backend alias and exact schema/table names. It
accepts no SQL, database URL or credential. Environment programs, reference answers
and verifiers stay protected. Oracles may be separate assets or embedded in the
protected verifier. JSON instructions retain their original source bytes and an
explicit top-level question key.

The file task transport and canonical file-recipe preparation reject state packs.
Workflow preview reports the missing controlled ToolHive/server and database
verifier binding. These are real remaining implementation requirements, not
functional readiness inferred from a catalog or preview.

## Original pinned packs

[Preparation](preparation.json) verifies the original Git blobs and SHA-256 hashes
for 11 cached assets, and checks local public/protected separation. No upstream
program, database, MCP server, container or model executes.

| Pack | Source pin | Oracle | Required output tables |
| --- | --- | --- | --- |
| [MCPMark](mcpmark-pack.json) | cd45b7f57923b9b3985467f5139927575f83141c | Original ground_truth.sql | security_audit_results; security_audit_details |
| [MCP-Universe](mcp-universe-pack.json) | 0df6c42717f2a618d34f5b271efd05be462b9e4d | Embedded expected findings in original verifier | security_audit_results; security_audit_details |

Each pack retains its own prompt and verifier. MCP-Universe's question omits
explicit table-schema deliverables present in MCPMark; that difference is
preserved and requires task-contract review before agent trials. Both verifiers
need the previously identified incomplete/empty-summary controls calibrated
against reference and destructive outputs. Original assertions remain unchanged;
any supplemental guard must be frozen and reported separately before trials.
These related snapshots are two integration targets, not independent usefulness
cases.

Repository notices are retained. Exact asset-use determinations, private runtime
closure, backend permissions, protected grader calls and cleanup remain open.
Reference execution has not occurred. Nothing here closes either MCP integration
or the complete-stack gate. Comparisons remain paused.

## Verification

All 13 source gates pass on working-tree source
`7424fc37900bfa06711b169b895b10c590b85ee5b574e3ea1165ce805fb0a6a0`.
Both full runs passed 2,115 tests with 21 skips; combined coverage is
82.65568708183221%, and both branch gates pass. Schemas, policy, lint, typing,
integration fixtures and build also pass. The checks use first-party substitutes;
no MCP database/server, upstream task or model ran. The separately pending SkillRank
continuation binds the unchanged checked f2c7a3e9 coordinator snapshot; these new
MCP edits are outside its scope. Passed wheel/docs results retain their original
source and checked-input versions.

[Exact commands and results](verification/checks.json) and the
[406-file source inventory](verification/source-inventory.json) bind the tested
working tree. It includes the operator's separate uncommitted development pin and
CI test, which remain outside this feature commit. Minimum sampled host free
space was 65.66 GiB. The new wheel was built, not installed; its SHA-256 is
`a73e5967dbfcc685949a7c65bef1ab0caff9a7aa572ba5e776eb264145e46832`.
The changed guide is outside the completed c022 documentation check; a new offline
check needs applicable authority before that documentation gate can close.

## Next runtime work

[ToolHive source/build preparation](toolhive-build-preparation.json) preserves
pin `33ba170aad633e20520f380500a45cd158f24aed`. Its Go requirement is 1.27.0;
the installed Go 1.27.1 binary has a recorded fingerprint. No compiler was run.
The pinned release configuration disables CGO. A read-only cache audit found none
of the 464 checksum-listed module archives available locally. Download, license,
build and service permission closure is still needed before an execution review.
No source pin was changed and no dependencies, images or services were created.
