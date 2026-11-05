# ToolHive loopback listener correction

The retained image and controller boundary passed. The actual ToolHive process
then rejected port 39068 before creating a container. That port was free for
TCP and UDP outside the controller profile. The exact profile returned
`EPERM` for both binds. The pinned upstream `networking.IsAvailable` checks
both protocols before the foreground launch.

The [review](operation-review.json) binds the same ToolHive executable and
server image with one port change to the controller profile. First-party socket
checks allow TCP and UDP on 39068 and deny both on 39069. The OS rule can also
permit a wildcard bind on 39068. The reviewed ToolHive arguments explicitly
bind the listener to `127.0.0.1`, and the driver verifies that exact listener
before any MCP message. Child container access and outbound denial stay the same.

The actual attempt is pending explicit repeat approval. It fits within the
original 37-operation and 1,800-second ceiling, with 17 operations already
charged. No build, download, installation, model or payment is included.
