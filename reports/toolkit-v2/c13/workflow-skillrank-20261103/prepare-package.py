"""Freeze the current wheel plus unchanged cached dependencies; never install."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import component_context as prepared
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, prepare, digest, check_closure
from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry

HERE, ROOT = prepared.HERE, prepared.ROOT
checks = prepared.load(HERE / 'verification/checks.json')
source = verification_source_digest(ROOT)
assert checks['source_before'] == checks['source_after'] == source
assert len(checks['checks']) == 13 and all(row['exit_code'] == 0 for row in checks['checks'])
assert not (HERE / 'package-installation.json').exists()
old = RuntimeInstallation.model_validate(prepared.load(HERE.parent / 'scanner-storage-review-20261103/package-installation.json'))
wheel = next((HERE / 'verification/dist').glob('*.whl'))
cache = prepared.WORK / 'package-wheels'
cache.mkdir(mode=0o700, parents=True)
metadata = {item.manifest.extension_id: item.manifest for item in old.preview.items}
groups = {'aeep': {}, 'aeep_toolkit': {}, 'integrations': {}}
with zipfile.ZipFile(wheel) as archive:
    for path in (ROOT / 'src').rglob('*.py'):
        if '__pycache__' not in path.parts and not any(part.endswith('.egg-info') for part in path.parts):
            assert archive.read(path.relative_to(ROOT / 'src').as_posix()) == path.read_bytes()
    for name in archive.namelist():
        if name.endswith('/') or '__pycache__' in name.split('/'):
            continue
        for label in ('aeep', 'aeep_toolkit'):
            if name.startswith(label + '/'):
                groups[label][name.removeprefix(label + '/')] = archive.read(name)
        prefix = 'aeep_agent_router-0.8.2.data/data/share/aeep/integrations/'
        if name.startswith(prefix):
            groups['integrations'][name.removeprefix(prefix)] = archive.read(name)
    expanded = sum(item.file_size for item in archive.infolist()) + wheel.stat().st_size
installed = hashlib.sha256(b'aeep.installed-source.v1\0')
for label, entries in sorted(groups.items()):
    assert entries
    for name, data in sorted(entries.items()):
        installed.update((label + '/' + name).encode() + b'\0')
        installed.update(hashlib.sha256(data).digest())
wheels = []
for original in old.wheels:
    path = wheel if original.extension_id == 'aeep-agent-router' else Path(old.wheelhouse) / original.filename
    sha = prepared.sha(path)
    assert original.extension_id == 'aeep-agent-router' or sha == original.sha256
    shutil.copyfile(path, cache / original.filename)
    wheels.append(original.model_copy(update={'sha256': sha}))
item = metadata['aeep-agent-router'].model_dump(mode='json')
item['source'].update(artifact_sha256=prepared.sha(wheel), revision=source)
item['disk_bytes'] = expanded
metadata['aeep-agent-router'] = ExtensionManifest.model_validate(item)
registry = ExtensionRegistry(extensions=tuple(metadata.values()))
policy = PreviewPolicy.model_validate(old.policy.model_dump(mode='json') | {
    'free_disk_bytes': shutil.disk_usage(ROOT).free,
    'reviewed_dependency_manifests': tuple(manifest_digest(m) for m in metadata.values())})
plan = prepare(preview(registry, ('aeep-agent-router',), policy, profile='essentials'),
    policy, prepared.WORK / 'installed-runtime', cache, tuple(wheels))
prepared.write(HERE / 'package-installation.json', plan.model_dump(mode='json'))
prepared.write(HERE / 'package-preparation.json', {'source': source, 'installed_source': installed.hexdigest(),
    'installation_digest': digest(plan), 'wheels': len(wheels), 'unchanged_dependencies': 32,
    'required_bytes': max(plan.preview.known_disk_bytes, 500*1024**2 + check_closure(cache, plan.wheels, policy.platform)),
    'executed': False, 'minimum_free_bytes': 50*1024**3})
work = HERE / 'package-execution/work'
work.mkdir(mode=0o700, parents=True)
for name in ('home', 'tmp'):
    (work / name).mkdir(mode=0o700)
profile = '(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n'
profile += '(allow file-write* (subpath ' + json.dumps(str(work)) + '))\n'
profile += '(deny file-read* (subpath ' + json.dumps(str(Path.home().resolve())) + '))\n'
for path in (Path(plan.destination), work):
    profile += '(allow file-read* (subpath ' + json.dumps(str(path)) + '))\n'
profile += '(allow file-read-metadata ' + ' '.join('(literal ' + json.dumps(str(p)) + ')'
    for p in dict.fromkeys((*Path(plan.destination).parents, *work.parents)) if p.is_relative_to(Path.home())) + ')\n'
(HERE / 'package.sb').write_text(profile)
print(json.dumps({'prepared': True, 'wheel': prepared.sha(wheel), 'wheels': len(wheels), 'installed_source': installed.hexdigest(), 'execution': False}))
