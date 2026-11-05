# ToolHive retained-image launch results

The approved continuation verified the exact image, passed the controller
boundary and ran the real ToolHive foreground command. ToolHive reported that
proxy port 39068 was unavailable and exited before creating a server container.
The [actual error](foreground-early-exit.json) and
[terminal verdict](summary.json) are retained.

The grant settled at 17 operations, zero model turns and 9.603700499981642
seconds. The image and runtime remain. The MCP list, invocation and normal
server stop checks did not run because launch failed. The next review is the
[loopback listener correction](../toolhive-loopback-bind-20261104/operation-review.json).
