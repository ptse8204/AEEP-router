"""Use installed Codex in an empty home; inspect/call MCP tools without a model turn."""
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from aeep.access import adopt_filter, change_access
from aeep.hosts.codex_app_server import CodexAppServerTransport
from aeep.onboarding import connect, disconnect, initialize

report = Path(__file__).parent
root = Path('/tmp/aeep-onboarding-continuation/codex').resolve()
binary = Path(shutil.which('codex')).resolve()
root.mkdir(exist_ok=False)
project = root / 'project'
project.mkdir()
subprocess.run(['git', 'init', '-q', str(project)], check=True)
home = root / 'home'
home.mkdir()
host_home = home / '.codex'
host_home.mkdir()
(host_home / 'config.toml').write_text('[projects.' + json.dumps(str(project)) + ']\ntrust_level = "trusted"\n')
os.environ.update({'HOME': str(home), 'CODEX_HOME': str(host_home), 'AEEP_CONFIG_HOME': str(home / 'aeep')})
initialize()
connect('alpha', 'codex', project)
connect('beta', 'codex', project)
change_access('beta', 'aeep_discovery_status', False)
record = {'scope': 'Isolated Codex App Server, no model request, no sign-in or existing auth state',
          'binary': str(binary), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'version': subprocess.check_output([str(binary), '--version'], text=True).strip(), 'workspace': str(root), 'checks': []}


def transport():
    return CodexAppServerTransport((str(binary), 'app-server'), environment_allowlist=('CODEX_HOME', 'PATH', 'HOME'),
                                   cwd=str(project), request_timeout=45)


async def inventory(client):
    status = await client.request('mcpServerStatus/list', {'limit': 20, 'detail': 'toolsAndAuthOnly'})
    return {row['name']: sorted(row['tools']) for row in status['data']}


async def main():
    client = transport()
    try:
        initial = await inventory(client)
        record['initial_inventory'] = initial
        assert 'aeep_discovery_status' in initial['aeep_alpha']
        assert 'aeep_discovery_status' not in initial['aeep_beta']
        record['checks'].append('two actual host connections expose different inventories')
        thread = await client.request('thread/start', {'ephemeral': True, 'cwd': str(project), 'approvalPolicy': 'never', 'sandbox': 'read-only'})
        call = {'threadId': thread['thread']['id'], 'server': 'aeep_alpha', 'tool': 'aeep_discovery_status', 'arguments': {}}
        first = await client.request('mcpServer/tool/call', call)
        assert not first.get('isError'), first
        record['checks'].append('actual Codex tool call succeeds before revocation')
        await asyncio.to_thread(change_access, 'alpha', 'aeep_discovery_status', False)
        denied = await client.request('mcpServer/tool/call', call)
        assert denied.get('isError'), denied
        record['checks'].append('cached host declaration cannot bypass live AEEP revocation')
    finally:
        await client.close()
    await asyncio.to_thread(adopt_filter, 'alpha', 'aeep_alpha', 'aeep_list_capabilities', deny=True)
    client = transport()
    try:
        hidden = await inventory(client)
        record['filtered_inventory'] = hidden
        assert 'aeep_discovery_status' not in hidden['aeep_alpha']
        assert 'aeep_list_capabilities' not in hidden['aeep_alpha']
        assert 'aeep_list_capabilities' in hidden['aeep_beta']
        record['checks'].append('native disabled_tools and AEEP denial both survive host reload')
    finally:
        await client.close()
    await asyncio.to_thread(adopt_filter, 'alpha', 'aeep_alpha', 'aeep_list_capabilities', deny=False)
    await asyncio.to_thread(change_access, 'alpha', 'aeep_discovery_status', True)
    client = transport()
    try:
        restored = await inventory(client)
        record['restored_inventory'] = restored
        assert 'aeep_discovery_status' in restored['aeep_alpha'] and 'aeep_list_capabilities' in restored['aeep_alpha']
        assert 'aeep_discovery_status' not in restored['aeep_beta']
        record['checks'].append('restoring alpha leaves beta denial intact')
    finally:
        await client.close()
    await asyncio.to_thread(disconnect, 'alpha')
    await asyncio.to_thread(disconnect, 'beta')
    client = transport()
    try:
        assert await inventory(client) == {}
        record['checks'].append('disconnected entries absent after host reload')
    finally:
        await client.close()


try:
    asyncio.run(main())
    record['status'] = 'passed'
except BaseException as exc:
    record.update(status='failed', error=repr(exc))
    raise
finally:
    (report / 'codex-result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
