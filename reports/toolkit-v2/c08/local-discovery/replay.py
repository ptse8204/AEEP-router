"""Bounded local discovery proof; candidate metadata is synthetic and never executed."""
import asyncio
import hashlib
import json
import socket
import subprocess
import tempfile
from pathlib import Path

from aeep.discovery import DiscoveryRequest
from aeep.discovery_service import DiscoveryConfig, DiscoveryService, DiscoverySourceConfig
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent

async def main():
    working = Path(tempfile.mkdtemp(prefix='aeep-discovery-proof-')).resolve()
    fixture = working / 'catalog.json'
    fixture.write_text(json.dumps({'candidates': [{
        'registry_candidate_id': 'synthetic-skill', 'name': 'Synthetic CSV helper',
        'version': '1.0', 'description': 'Untrusted fixture metadata',
        'package_locator': {'kind': 'https', 'value': 'https://example.invalid/never-run.zip'},
        'provenance': {'entry': {'type': 'skill', 'verified': True}},
    }]}))
    store = ReceiptStore(working / 'discovery.sqlite3')
    service = DiscoveryService.from_config(store, DiscoveryConfig(sources=[
        DiscoverySourceConfig(source_id='local', kind='fixture', path=str(fixture)),
        DiscoverySourceConfig(source_id='remote-denied', kind='ard', base_url='https://example.invalid', allow_remote=False),
    ]))
    original_socket, original_popen = socket.socket, subprocess.Popen
    def denied(*args, **kwargs):
        raise AssertionError('local discovery attempted network or process execution')
    socket.socket, subprocess.Popen = denied, denied
    try:
        result = await service.search(DiscoveryRequest(public_query='CSV', source_ids=['local'], limit=1))
        assert result.candidate_ids == ['synthetic-skill']
        assert service.get(result.discovery_id) == result
        errors = {}
        for source in ('unconfigured', 'remote-denied'):
            try:
                await service.search(DiscoveryRequest(public_query='CSV', source_ids=[source], limit=1))
            except ConfigurationError as exc:
                errors[source] = str(exc)
            else:
                raise AssertionError('unavailable or unauthorized source ran')
        counts = {table: store._connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                  for table in ('assessment_jobs', 'assessment_grants', 'assessment_admissions')}
        assert not any(counts.values())
        evidence = {'source_commit': subprocess_source_commit, 'kind': 'synthetic_local_discovery',
                    'working_directory': str(working), 'result': result.model_dump(mode='json'),
                    'rejections': errors, 'assessment_counts': counts,
                    'candidate_code_executed': False, 'network_or_child_process_calls': 0,
                    'source_hashes': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                      for name in ('src/aeep/discovery.py', 'src/aeep/discovery_service.py')},
                    'limitations': ['Not a remote registry conformance result.', 'Scanner is not installed or qualified.', 'Metadata claims do not authorize candidate installation.']}
        (OUT/'result.json').write_text(json.dumps(evidence, indent=2)+'\n')
    finally:
        socket.socket, subprocess.Popen = original_socket, original_popen
        store.close()

subprocess_source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
asyncio.run(main())
