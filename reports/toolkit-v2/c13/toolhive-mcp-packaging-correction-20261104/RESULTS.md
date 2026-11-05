# The image build passed; the following record write stopped the driver

Approved review 96552b4e built the retained formatting-server image successfully:
`aeep-toolkit-v2/toolhive-mcp:formatting-control-20261104`, image ID
`sha256:3c0b4f876d9148e5a037033a3dbf60c5075a4cce8a251447d729546bacfda1ff`.
Read-only inspection confirms the inherited parent layers, the intended Python
entrypoint and user 65534:65534. No rebuild is needed.

The next build-record write used HERE/server.py instead of the bound external
source path. That FileNotFoundError ended the driver before any native profile,
ToolHive controller, MCP server or MCP client ran. The cumulative grant retains
11 operations / zero models / 8.105458749458194 seconds, with no accounting or
cleanup uncertainty. The output image and both owned build contexts remain.
Docker-internal temporary build identities were not retained by the driver;
unknown resources must be preserved rather than inferred obsolete.

The next continuation reads source/profile paths from explicit reviewed bindings
and validates them before dispatch. Five first-party preparation checks cover
relocation, missing/drifted source, changed image and the original source-path
regression. They ran no external executable or model. Actual MCP launch,
permission checks, AEEP invocation and stop remain unverified.
