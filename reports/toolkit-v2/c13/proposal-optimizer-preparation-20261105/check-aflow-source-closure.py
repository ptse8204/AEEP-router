"""Retain the benchmark code imported by the pinned optimizer without loading it."""

import ast
import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name / 'aflow-runtime-inputs'
prior = json.loads((HERE / 'aflow-runtime-inputs-result.json').read_bytes())
assert prior['passed'] and not prior['guest_code_executed']
archive = WORK / 'source.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == prior['source_archive']['sha256']
revision = prior['source_revision']
url = f'https://api.github.com/repos/FoundationAgents/AFlow/git/trees/{revision}?recursive=1'
with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AEEP source closure review'}), timeout=15) as response:
    raw = response.read(2_000_001)
assert len(raw) <= 2_000_000
tree = json.loads(raw)
assert tree['sha'] == revision and not tree['truncated']
entries = {row['path']: row for row in tree['tree'] if row['type'] == 'blob' and row['path'].startswith('benchmarks/')
           and row['path'].endswith('.py') and row['mode'] in ('100644', '100755')}
assert 1 <= len(entries) <= 100 and sum(x['size'] for x in entries.values()) <= 1024**2
observed = {}
with tarfile.open(archive, 'r:gz') as source:
    for item in source:
        path = PurePosixPath(item.name)
        assert not path.is_absolute() and '..' not in path.parts
        name = '/'.join(path.parts[1:])
        if name not in entries:
            continue
        assert item.isfile() and name not in observed and item.size == entries[name]['size']
        reader = source.extractfile(item)
        assert reader is not None
        data = reader.read(item.size + 1)
        assert hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() == entries[name]['sha']
        ast.parse(data)
        output = WORK / 'source' / name
        output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with output.open('xb') as f:
            f.write(data)
        output.chmod(0o444)
        observed[name] = {'git_blob':entries[name]['sha'],'sha256':hashlib.sha256(data).hexdigest()}
assert set(observed) == set(entries)
imports = set()
for path in (WORK / 'source').rglob('*.py'):
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            imports.update(item.name.split('.')[0] for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module.split('.')[0])
third_party = imports - sys.stdlib_module_names - {'scripts', 'benchmarks'}
resolved = set()
for row in json.loads((HERE / 'aflow-wheel-acquisition-result.json').read_bytes())['artifacts']:
    name = row['name'].lower().replace('-', '_')
    resolved.add('yaml' if name in {'pyyaml','pyaml'} else name)
result = {'source_revision':revision,'source_archive_sha256':prior['source_archive']['sha256'],
          'tree_metadata_sha256':hashlib.sha256(raw).hexdigest(),'source_files':observed,
          'observed_static_external_imports':sorted(third_party),'not_in_wheel_lock_or_standard_library':sorted(third_party-resolved),
          'verification_scope':'AST imports across selected source. Conditional and generated imports need runtime review.',
          'benchmarks_data_copied':False,'runtime_installed':False,'code_executed':False,'models':0}
with (HERE / 'aflow-source-closure.json').open('x') as f:
    json.dump(result,f,indent=2)
    f.write('\n')
print({'benchmark_sources_verified':len(observed),'unresolved_static_imports':result['not_in_wheel_lock_or_standard_library']})
