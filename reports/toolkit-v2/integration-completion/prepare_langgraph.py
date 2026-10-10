"""Prepare a private wheel review; downloads inert wheels, never installs/imports them."""
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from email.parser import BytesParser
from graphlib import TopologicalSorter
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from aeep_toolkit.install_runtime import Wheel, check_closure, digest, prepare, wheel_commands
from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry

HERE = Path(__file__).resolve().parent / 'langgraph-review-v2'
HERE.mkdir(exist_ok=False)
root = Path('/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/aeep-langgraph-reviewed-swz3r645')
assert shutil.disk_usage(root).free > 50*1024**3 + 1024**3
report = json.loads(Path('/tmp/aeep-langgraph-review.json').read_text())
packages = {}
wheels = []
for entry in report['install']:
    url = entry['download_info']['url']
    expected = entry['download_info']['archive_info']['hashes']['sha256']
    filename = url.rsplit('/', 1)[-1]
    raw = (root/filename).read_bytes() if (root/filename).is_file() else urllib.request.urlopen(url, timeout=30).read(16*1024**2)
    assert hashlib.sha256(raw).hexdigest() == expected
    path = root/filename; path.write_bytes(raw)
    with zipfile.ZipFile(path) as archive:
        header = next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
        meta = BytesParser().parsebytes(archive.read(header))
        licenses = {n: hashlib.sha256(archive.read(n)).hexdigest() for n in archive.namelist()
                    if not n.endswith('/') and ('license' in n.casefold() or 'notice' in n.casefold())}
        license_name = meta.get('License-Expression') or meta.get('License')
        assert license_name and len(license_name) < 200
        name = canonicalize_name(meta['Name'])
        dependencies = []
        for value in meta.get_all('Requires-Dist', []):
            requirement = Requirement(value)
            if not requirement.marker or requirement.marker.evaluate({'extra': ''}):
                dependencies.append(canonicalize_name(requirement.name))
        packages[name] = {'name': name, 'version': meta['Version'], 'url': url, 'sha256': expected,
                          'archive_bytes': len(raw), 'expanded_bytes': sum(i.file_size for i in archive.infolist()),
                          'license': license_name, 'license_files': licenses,
                          'dependencies': dependencies, 'requires_dist': meta.get_all('Requires-Dist', [])}
        wheels.append(Wheel(extension_id=name, name=meta['Name'], version=meta['Version'], filename=filename, sha256=expected))
for wheel in wheels:
    packages[canonicalize_name(wheel.name)]['private_commands'] = wheel_commands(root/wheel.filename, wheel)
rights = 'Private local verification only; preserve bundled license notices. No redistribution reviewed.'
manifest = {}
for name in TopologicalSorter({name: p['dependencies'] for name, p in packages.items()}).static_order():
    p = packages[name]
    manifest[name] = ExtensionManifest(extension_id=name, purpose='Optional LangGraph fixture runtime: '+name,
        role='orchestrator' if name=='langgraph' else 'support',
        source={'repository':p['url'],'revision':p['sha256'],'artifact_sha256':p['sha256'],
                'license_expression':p['license'],'data_rights':rights},
        hosts=('local-python',), platforms=('darwin-arm64',),
        dependencies=tuple({'extension_id':dep,'manifest_sha256':manifest_digest(manifest[dep])} for dep in p['dependencies']),
        permissions={'network_destinations':[],'filesystem_scope':'workspace','authentication':'none','financial_exposure':'none'},
        disk_bytes=p['archive_bytes']+p['expanded_bytes'], memory_bytes=None,
        install_effects=('Private runtime only. No activation, model calls, telemetry destination or host configuration.',),
        rollback='Remove only unchanged owned runtime through existing installer; preserve journal and conflicts.',status='not_installed')
registry=ExtensionRegistry(extensions=tuple(manifest.values()))
policy=PreviewPolicy(host='local-python',platform='darwin-arm64',
    allowed_licenses=tuple(sorted({p['license'] for p in packages.values()})),allowed_data_rights=(rights,),
    allowed_filesystem_scopes=('workspace',),free_disk_bytes=shutil.disk_usage(root).free,allow_unknown_memory=True,
    reviewed_dependency_manifests=tuple(manifest_digest(m) for m in manifest.values()))
plan=preview(registry,('langgraph',),policy,profile='full')
installation=prepare(plan,policy,root/'runtime',root,tuple(wheels))
for name,value in [('packages',list(packages.values())),('installation',installation.model_dump(mode='json')),
                   ('review',{'review_sha256':digest(installation),'wheel_count':len(wheels),'downloaded_bytes':sum(p['archive_bytes'] for p in packages.values()),
                              'reserve_bytes':500*1024**2+check_closure(root,tuple(wheels),policy.platform),
                              'runtime_created':False,'source_revision':'40a2e6d845054cc0cc17a6a169ca6e7394e5231c',
                              'source_matches_wheel':False,'reason':'Source pyproject requires checkpoint>=4.3; wheel metadata permits >=4.1. Runtime review uses exact wheel hashes, not source equivalence.'})]:
    (HERE/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
print((HERE/'review.json').read_text())
