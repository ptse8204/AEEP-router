"""Exercise only an isolated, installed AEEP service; no model or provider calls."""
import asyncio
import json
import os
from pathlib import Path

from aeep.access import change_access
from aeep.catalogs import catalog_path
from aeep.connections import connection_path
from aeep.errors import ProtocolError
from aeep.mcp.client import MCPStdioClient
from aeep.onboarding import connect, disconnect

root = Path('/tmp/aeep-onboarding-build/release-final-check').resolve()
os.environ['AEEP_CONFIG_HOME'] = str(root / 'home/config')
connection = connect('stdio-probe', 'deepseek-api', root / 'project')
change_access('stdio-probe', 'aeep_discovery_status', True)


async def main():
    client = MCPStdioClient(command=str(root / 'home/data/venv/bin/python'), args=[
        '-I', '-m', 'aeep', 'serve', '--manifest', connection.manifest,
        '--connection', str(connection_path('stdio-probe')), '--discovery-config', str(catalog_path())])
    try:
        names = {t['name'] for t in (await client.list_tools()).result['tools']}
        assert 'aeep_discovery_status' in names and 'aeep_execute_action' not in names
        assert not (await client.call_tool('aeep_discovery_status', {})).result.get('isError')
        await asyncio.to_thread(change_access, 'stdio-probe', 'aeep_discovery_status', False)
        assert 'aeep_discovery_status' not in {t['name'] for t in (await client.list_tools()).result['tools']}
        try:
            rejected = (await client.call_tool('aeep_discovery_status', {})).result
        except ProtocolError as exc:
            assert 'Unknown tool' in str(exc)
        else:
            assert rejected['isError']
        return {'status': 'passed', 'protocol': client.protocol_version, 'checks': ['installed process initialization', 'filtered tool inventory', 'operator revocation while server runs', 'stale declaration denied'], 'host_reload': 'not tested'}
    finally:
        await client.close()
        await asyncio.to_thread(disconnect, 'stdio-probe')


if __name__ == '__main__':
    print(json.dumps(asyncio.run(main()), indent=2))
