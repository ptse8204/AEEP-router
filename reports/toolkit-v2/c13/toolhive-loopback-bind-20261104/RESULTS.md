# ToolHive launched, verified and stopped the reviewed MCP server

The actual ToolHive process opened the sole TCP listener at
`127.0.0.1:39068`. It listed both reviewed tools and invoked the permission
probe. The probe read the allowed input, denied writes and external access,
and could not see the Docker socket or host canary. The server ran as UID 65534
with no network and a read-only input mount. Its private root filesystem was
writable, and ToolHive did not set no-new-privileges.

AEEP's existing MCP executor invoked `format_json` and verified the result.
The ToolHive stop command completed and cleanup verified the owned container
was stopped or removed. The binary, image and unrelated Docker resources
remain. This is [component lifecycle evidence](summary.json) on the reviewed
first-party formatting control. The two upstream benchmark journeys and
paired-agent isolation qualification require separate evidence.

The existing grant settled at 32 operations, zero model turns and
43.33603483438492 seconds. The last attempt added 15 operations.
