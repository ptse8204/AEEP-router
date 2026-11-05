# PostgreSQL backend for the two MCP reference tasks

The pinned MCPMark Dockerfile selects `postgres-mcp==0.3.0`. The pinned
MCP-Universe task selects `postgres-pro`, whose source launches the same
package with unrestricted access and without a version pin. Reusing 0.3.0 is
a compatibility candidate for MCP-Universe and needs a functional check.

The [source and wheel record](metadata.json) binds the exact public package,
dependency requirements, license-file hash and real console entry point.
The wheel is cached privately without import or installation. Resolve its
transitive closure and the protected verifiers' psycopg2 dependency next.

Use a new owned PostgreSQL instance for each pack. The original seed scripts
can terminate database sessions and remove matching roles or databases.
Keep them outside the MCP client and protect the verifier and reference
answers. Use the existing ToolHive and AEEP MCP transport only after binding
the server to that isolated instance. Preserve each pack's own grading and
the distinction between a reference run and a usefulness trial.
