"""Upgrade only the earlier isolated installer fixture and verify durable state."""
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

root = Path('/tmp/aeep-onboarding-build/isolated-home').resolve()
project = Path('/tmp/aeep-onboarding-build/isolated-project').resolve()
manifest = root / 'config/config.yaml'
from aeep.config import load_manifest
config, _ = load_manifest(manifest)
database = Path(config.database)
if not database.is_absolute():
    database = manifest.parent / database
with sqlite3.connect(database) as db:
    before_records = dict(((kind, identity), payload) for kind, identity, payload in db.execute('SELECT kind,id,payload_json FROM assessment_records'))
before_manifest = manifest.read_bytes()
before_catalog = (root / 'config/discovery.json').read_bytes()
connection = root / 'config/connections/deepseek-api.json'
before_filters = json.loads(connection.read_text())['allowed_tools']
previous_runtime = (root / 'data/venv').resolve()
release = Path('dist/v0.8.2-onboarding-final').resolve()
env = {'PATH': os.environ['PATH'], 'HOME': str(root), 'AEEP_DATA_HOME': str(root / 'data'),
       'AEEP_CONFIG_HOME': str(root / 'config'), 'UV_PYTHON_PREFERENCE': 'only-managed'}
subprocess.run(['sh', str(release / 'install.sh'), '--bundle', str(release / 'bundle'), '--agent', 'deepseek-api', '--project', str(project), '--yes'], env=env, check=True, timeout=300)
assert manifest.read_bytes() == before_manifest
assert (root / 'config/discovery.json').read_bytes() == before_catalog
assert json.loads(connection.read_text())['allowed_tools'] == before_filters
assert (root / 'data/venv').resolve() != previous_runtime
marker = json.loads((root / 'data/installation.json').read_text())
assert Path(marker['previous_runtime']).resolve() == previous_runtime
with sqlite3.connect(database) as db:
    after_records = dict(((kind, identity), payload) for kind, identity, payload in db.execute('SELECT kind,id,payload_json FROM assessment_records'))
assert before_records.items() <= after_records.items()
Path('reports/v08/onboarding-20261006/upgrade-result.json').write_text(json.dumps({'status': 'passed', 'preserved_records': len(before_records), 'manifest_sha256': hashlib.sha256(before_manifest).hexdigest(), 'catalog_preserved': True, 'filters_preserved': True, 'previous_runtime': str(previous_runtime), 'runtime': marker['runtime'], 'rollback': marker['previous_runtime'], 'fixture_scope': 'Earlier isolated 0.8.2 candidate upgraded to final candidate; no production state'}, indent=2) + '\n')
