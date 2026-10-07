"""Reviewed reference package installation in a disposable home; no model or credentials."""
import asyncio
import json
import os
from pathlib import Path

from aeep.assessment.repository import AssessmentRepository
from aeep.component_setup import ComponentSetup, apply, define
from aeep.discovery import RegistryCandidate, _metadata_digest
from aeep.mcp.client import MCPStdioClient
from aeep.models import utc_now
from aeep.onboarding import connect, initialize
from aeep.router import Router

report = Path(__file__).parent
root = Path('/tmp/aeep-onboarding-continuation/components').resolve()
root.mkdir(exist_ok=False)
home, project = root / 'home', root / 'project'
home.mkdir(); project.mkdir()
path = os.environ['PATH']
os.environ.clear()
os.environ.update({'PATH': path, 'HOME': str(home), 'AEEP_CONFIG_HOME': str(home / 'aeep'), 'PIP_DISABLE_PIP_VERSION_CHECK': '1'})
initialize()
connection = connect('components', 'deepseek-api', project)
router = Router.from_manifest(connection.manifest)
results = []


async def check(entry, tool, arguments):
    client = MCPStdioClient(command=entry['command'], args=entry['args'], env=dict(os.environ), cwd=str(project), timeout=30)
    try:
        names = sorted(t['name'] for t in (await client.list_tools()).result['tools'])
        assert tool in names, names
        result = (await client.call_tool(tool, arguments)).result
        assert not result.get('isError'), result
        return {'protocol': client.protocol_version, 'tools': names, 'read_only_call': tool, 'call_result': result}
    finally:
        await client.close()


try:
    for kind, executable, tool, arguments in [
        ('python', 'mcp-server-time', 'get_current_time', {'timezone': 'UTC'}),
        ('npm', 'mcp-server-memory', 'read_graph', {}),
    ]:
        metadata = json.loads((report / (kind + '-metadata.json')).read_text())
        candidate = RegistryCandidate(registry_candidate_id='reference-' + kind, adapter_id='operator-public-metadata',
            name=metadata['name'], version=metadata['version'], description=metadata.get('summary',metadata.get('description','')),
            provenance={'metadata_url': metadata['metadata_url'], 'availability': 'unverified'}, retrieved_at=utc_now(),
            raw_metadata_digest=_metadata_digest(metadata))
        router.store.save_registry_candidate(candidate)
        plan = ComponentSetup(connection_id='components', candidate_id=candidate.registry_candidate_id,
            candidate_digest=candidate.raw_metadata_digest, kind=kind, package=metadata['name'], version=metadata['version'],
            executable=executable)
        preview = define(router, plan)
        (report / (kind + '-preview.json')).write_text(json.dumps(preview,indent=2)+'\n')
        AssessmentRepository(router.store).review(preview['digest'])
        installed = apply(router, preview['digest'])
        assert installed['status'] == 'installed'
        assert apply(router, preview['digest']) == installed
        descriptor = project / '.aeep' / ('aeep_component_' + preview['digest'][:16] + '.json')
        entry = json.loads(descriptor.read_text())
        checked = asyncio.run(check(entry, tool, arguments))
        assert installed['execution'] == 'not admitted; host connection only'
        results.append({'kind': kind, 'package': plan.package, 'version': plan.version, 'setup': installed, 'probe': checked,
                        'lifecycle_scripts': False, 'repeat_apply': 'idempotent'})
        (report / 'components-result.json').write_text(json.dumps({'status':'running', 'components':results},indent=2)+'\n')
    (report / 'components-result.json').write_text(json.dumps({'status':'passed','workspace':str(root),'components':results,
        'scope':'Application descriptors plus direct isolated MCP checks; no API model loop or routing admission'},indent=2)+'\n')
finally:
    asyncio.run(router.close())
