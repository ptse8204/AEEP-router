"""Minimal dual-era MCP client primitives used by AEEP.

Server objects live in :mod:`aeep.mcp.server` and are intentionally not imported
here, avoiding a cycle while the Router constructs MCP executors.
"""

from .client import LEGACY_VERSION, MODERN_VERSION, MCPHTTPClient, MCPStdioClient

__all__ = [
    "LEGACY_VERSION",
    "MCPHTTPClient",
    "MCPStdioClient",
    "MODERN_VERSION",
]
