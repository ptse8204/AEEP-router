# Retained Postgres MCP 0.3.0 runtime candidate

The MCPMark source pins Postgres MCP 0.3.0. The wheel pins
`pglast==7.2.0`. The binary-only resolution stopped because PyPI no longer
serves that version. The attempted resolution also selected MCP SDK 2.3.0,
which the upstream project's [compatibility issue](https://github.com/crystaldba/postgres-mcp/issues/187)
identifies as incompatible with this release. Keep the server pin and inspect
the [publisher's 0.3.0 image](https://hub.docker.com/r/crystaldba/postgres-mcp/tags)
instead of upgrading either dependency.

The [registry and wheel record](upstream-artifacts.json) binds the release
tag, Linux amd64 manifest, config, layer diff IDs and exact protected
psycopg2-binary 2.9.10 wheel. The actual image pull succeeded. The
[original acquisition](acquisition/summary.json) flagged the image because
its repository-digest guard expected the Docker Hub prefix. A separate
[read-only identity check](retained-image-identity.json) matched the
normalized name, digest, all eight layers and entry point. Preserve the
three charged operations and the original outcome. The image remains
available with no repull. Its bundled runtime and licensing still need
inspection. The image's license label and the wheel's license metadata
differ, so preserve and verify the corresponding notices separately.

Both pinned upstream tasks generate their database fixtures in their
original preparation scripts. Retain their repository notices, original
inputs and protected verifier bytes. Each pack needs a fresh owned database
with a separate internal network or private socket. The preparation
programs can terminate sessions and remove databases or roles. Bind them
only to their owned database and keep the server's SQL access inside that
boundary. Keep the reference SQL, verifier and output contents out of the
MCP client. MCPMark's separate oracle and MCP-Universe's embedded
expectations remain distinct. The two related tasks are not independent
usefulness cases.

This record covers artifact preparation. Both benchmark journeys still
require the actual database setup, reviewed MCP invocation, protected
grading and terminal state receipts. No server, task or model executed.

The [bundled runtime audit](bundled-runtime-audit.json) read the image
archive without starting a container. It matched Postgres MCP 0.3.0,
pglast 7.2, MCP SDK 1.6.0, psycopg 3.2.6 and instructor 1.7.9 to the
publisher's exact release lock. This establishes that the image contains
the missing pinned dependency. Verify the bundled notices and the
database, server and verifier behavior in the next scoped run.
