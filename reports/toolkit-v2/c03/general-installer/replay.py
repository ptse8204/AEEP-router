"""Replay D19's exact 24 approved wheels through the general installer, offline."""
import hashlib
import json
import shutil
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

from aeep_toolkit.install_runtime import Wheel, apply, digest, prepare, remove
from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
CACHE = Path('/private/tmp/aeep-toolkit-wheel-audit-ofr3udoo')
packages = json.loads((ROOT/'integrations/toolkit/packages.json').read_text())
by_hash = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in CACHE.glob('*.whl')}
items, wheels, licenses = [], [], []
for package in packages:
    archive = by_hash[package['sha256']]
    with zipfile.ZipFile(archive) as contents:
        meta = next(n for n in contents.namelist() if n.endswith('.dist-info/METADATA'))
        headers = BytesParser().parsebytes(contents.read(meta), headersonly=True)
        license_files = {name: hashlib.sha256(contents.read(name)).hexdigest()
                         for name in contents.namelist() if 'LICENSE' in name}
        license_name = package['license']
        if license_name is None:
            text = '\n'.join(contents.read(n).decode() for n in license_files)
            assert package['name'] in {'markdown-it-py', 'mdurl'} and 'Permission is hereby granted, free of charge' in text
            license_name = 'MIT'
        expanded = sum(i.file_size for i in contents.infolist())
    licenses.append({'package': package['name'], 'license': license_name, 'wheel_sha256': package['sha256'], 'license_files': license_files})
    identity = 'python.'+package['name']
    wheel = Wheel(extension_id=identity, filename=archive.name, name=headers['Name'], version=headers['Version'], sha256=package['sha256'])
    wheels.append(wheel)
    items.append(ExtensionManifest(extension_id=identity, purpose='D19 approved evaluator wheel closure',
        role='evaluator' if package['name']=='agent-skill-eval' else 'support',
        source={'repository': 'https://pypi.org/project/'+package['name']+'/', 'revision': package['sha256'],
                'artifact_sha256': package['sha256'], 'license_expression': license_name, 'data_rights': 'local package installation; no benchmark data'},
        hosts=('codex',), platforms=('macos-arm64-python3.13',), dependencies=(),
        permissions={'network_destinations': [], 'filesystem_scope': 'workspace', 'authentication': 'none', 'financial_exposure': 'none'},
        disk_bytes=expanded*3+archive.stat().st_size*2, memory_bytes=512*1024**2,
        install_effects=('Install this exact wheel into the private runtime.', 'Memory is a conservative planning allowance, not a measured runtime figure.'),
        rollback='Remove only the unchanged owned runtime; retain journal and preserve all conflicts.', status='experimental'))
engine = next(i for i in items if i.role=='evaluator')
engine.dependencies = tuple({'extension_id':i.extension_id,'manifest_sha256':manifest_digest(i)} for i in items if i!=engine)
# Reparse nested model assignments so the serialized plan uses validated dependency objects.
registry = ExtensionRegistry.model_validate({'extensions':[i.model_dump(mode='json') for i in items]})
policy = PreviewPolicy(host='codex', platform='macos-arm64-python3.13', allowed_licenses=tuple(sorted({r['license'] for r in licenses})),
    allowed_data_rights=('local package installation; no benchmark data',), allowed_filesystem_scopes=('workspace',),
    free_disk_bytes=shutil.disk_usage(CACHE).free, reviewed_dependency_manifests=tuple(manifest_digest(i) for i in registry.extensions))
selection = preview(registry, (engine.extension_id,), policy)
parent = Path(tempfile.mkdtemp(prefix='aeep-general-installer-replay-')).resolve()
plan = prepare(selection, policy, parent/'runtime', CACHE, tuple(wheels))
(OUT/'installation.json').write_text(json.dumps({'review_sha256':digest(plan),'installation':plan.model_dump(mode='json')},indent=2)+'\n')
(OUT/'licenses.json').write_text(json.dumps(licenses,indent=2)+'\n')
state = apply(plan,digest(plan))
assert apply(plan,digest(plan)) == state
removed = remove(plan,digest(plan))
(OUT/'replay-result.json').write_text(json.dumps({'installed':state,'removed':removed,'runtime_preserved':False,
    'journal_directory_retained':str(parent),'wheel_count':len(wheels),'network':'no index; local wheels only'},indent=2)+'\n')
print(json.dumps({'installed_wheels':len(wheels),'idempotent_replay':True,'removed_unchanged_runtime':True,'journal':str(parent)}))
