"""A connection-bound bridge for DeepSeek and other function-call applications."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..connections import load_connection
from ..integrations import export_tools
from ..mcp.server import AEEPToolService
from ..router import Router


class ConnectedTools:
    def __init__(self, connection: Path) -> None:
        value = load_connection(connection)
        self.router = Router.from_manifest(value.manifest)
        self.service = AEEPToolService(self.router, connection=connection, discovery_config=connection.resolve().parent.parent / 'discovery.json')

    def declarations(self, format: str = 'deepseek') -> list[dict[str, Any]]:
        allowed = {item['name'] for item in self.service.list_tools()}
        return [item for item in export_tools(format)  # type: ignore[arg-type]
                if item.get('name', item.get('function', {}).get('name')) in allowed]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.service.call(name, arguments)

    async def close(self) -> None:
        await self.router.close()
