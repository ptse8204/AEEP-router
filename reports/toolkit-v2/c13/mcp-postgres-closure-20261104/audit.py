"""Bind the common MCP backend and inspect its published wheel without importing it."""
import ast
import email.parser
import hashlib
import json
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep/mcp-postgres-closure-20261104'
MARK_REVISION = 'cd45b7f57923b9b3985467f5139927575f83141c'
UNIVERSE_REVISION = '0df6c42717f2a618d34f5b271efd05be462b9e4d'
SERVER_WHEEL = 'postgres_mcp-0.3.0-py3-none-any.whl'
SERVER_SHA = '455dd71ed8deab77a67af2468e6f059dd0f114e05c0031ab47306a7048dc30bf'


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(
        url, headers={'User-Agent': 'AEEP-source-review'},
    ), timeout=20) as response:
        raw = response.read(1024**2 + 1)
    assert len(raw) <= 1024**2
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


mark_docker = f'https://raw.githubusercontent.com/eval-sys/mcpmark/{MARK_REVISION}/Dockerfile'
universe_config = ('https://raw.githubusercontent.com/SalesforceAIResearch/MCP-Universe/'
                   f'{UNIVERSE_REVISION}/mcpuniverse/mcp/configs/server_list.json')
mark = fetch(mark_docker)
assert b'pipx install postgres-mcp==0.3.0' in mark
universe = fetch(universe_config)
mapping = json.loads(universe)['postgres-pro']['stdio']
assert mapping == {'command': 'uvx', 'args': [
    'postgres-mcp', '{{POSTGRES_ADDRESS}}', '--access-mode', 'unrestricted',
]}
task = next((ROOT / '.aeep/mcp-stack-protected-candidate-20261103/SalesforceAIResearch__MCP-Universe')
            .rglob('user_permission_audit.json'))
assert json.loads(task.read_bytes())['mcp_servers'] == [{'name': 'postgres-pro'}]
package_url = 'https://pypi.org/pypi/postgres-mcp/0.3.0/json'
package = fetch(package_url)
wheel = next(x for x in json.loads(package)['urls'] if x['filename'] == SERVER_WHEEL)
assert wheel['digests']['sha256'] == SERVER_SHA and wheel['size'] == 91091
assert wheel['url'].startswith('https://files.pythonhosted.org/')
payload = fetch(wheel['url'])
assert sha(payload) == SERVER_SHA and len(payload) == wheel['size']
notice = {}
with zipfile.ZipFile(BytesIO(payload)) as archive:
    names = archive.namelist()
    dist_info = 'postgres_mcp-0.3.0.dist-info/'
    meta = email.parser.BytesParser().parsebytes(archive.read(dist_info+'METADATA'))
    assert meta['Name'] == 'postgres-mcp' and meta['Version'] == '0.3.0'
    source = archive.read('postgres_mcp/__init__.py')
    ast.parse(source)
    for name in names:
        if name.startswith(dist_info) and 'license' in name.lower() and not name.endswith('/'):
            notice[name] = sha(archive.read(name))
    entries = archive.read(dist_info+'entry_points.txt').decode()
with (WORK / SERVER_WHEEL).open('xb') as file:
    file.write(payload)
result = {
    'sources': {mark_docker: sha(mark), universe_config: sha(universe), package_url: sha(package)},
    'mcpmark_selected_version': '0.3.0',
    'mcp_universe_selected_backend': 'postgres-pro',
    'mcp_universe_upstream_version': 'unpinned',
    'compatibility_candidate': 'Try the same upstream server at the MCPMark pin. Confirm against both tasks before readiness.',
    'wheel': {'url': wheel['url'], 'sha256': SERVER_SHA, 'bytes': len(payload),
              'requirements': meta.get_all('Requires-Dist'), 'requires_python': meta['Requires-Python'],
              'license_fields': {k: meta[k] for k in ('License', 'License-Expression') if meta[k]},
              'license_file_hashes': notice, 'entry_points': entries},
    'runtime_limits': 'Only a fresh owned database may receive unrestricted SQL. Original preparation scripts can terminate connections and drop matching databases or roles.',
    'upstream_imported_or_executed': False, 'dependency_installation': False,
    'models': 0, 'comparisons': 'PAUSED',
}
with (HERE / 'metadata.json').open('x') as out:
    json.dump(result, out, indent=2)
    out.write('\n')
print(json.dumps({'wheel': SERVER_SHA, 'requires_python': result['wheel']['requires_python'],
                  'entry_points': entries, 'license_file_count': len(notice)}))
