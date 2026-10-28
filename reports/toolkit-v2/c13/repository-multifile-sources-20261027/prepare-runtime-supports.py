"""Close selected dependency pins with existing observations;prepare data only."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    raw=json.loads((HERE/'runtime-wheel-read.json').read_text());pins=[r for r in raw['pins'] if 'error_type' not in r];assert len(pins)==8
    source=json.loads((HERE/'untokenize-source-review.json').read_text());sdist=ROOT/source['sdist_cache'];assert sha(sdist)==source['sdist_sha256']
    with tarfile.open(sdist,'r:gz') as archive:
        files={m.name.split('/',1)[-1]:archive.extractfile(m).read() for m in archive if m.isfile()}
    module=ROOT/source['module_cache'];assert module.read_bytes()==files['untokenize.py']
    # Retain the upstream in-file permission notice;copy publisher PKG-INFO
    # unchanged as METADATA. No version or dependency statement is invented.
    notice=files['untokenize.py'].split(b'"""',1)[0];assert b'Permission is hereby granted' in notice
    license=HERE/'licenses/untokenize/LICENSE.source';license.parent.mkdir(parents=True,exist_ok=True);license.write_bytes(notice)
    metadata=HERE/'licenses/untokenize/PKG-INFO';metadata.write_bytes(files['PKG-INFO'])
    source.update(licenses=[{'path':str(license.relative_to(ROOT)),'sha256':sha(license)}],publisher_metadata_path=str(metadata.relative_to(ROOT)),publisher_metadata_sha256=sha(metadata),proposed_integration='COPY unchanged upstream module,in-file permission notice and exact publisher PKG-INFO as dist-info METADATA. No setup.py,source build or source changes. Metadata identifies a source copy,not a wheel installation.',distribution_metadata_installed=False)
    (HERE/'untokenize-source-review.json').write_text(json.dumps(source,indent=2)+'\n')
    prior=ROOT/'reports/toolkit-v2/c13/repository-worker-input-20261027';review=json.loads((prior/'operation-review.json').read_text());probe=review['probes'][0]['payload']
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(probe['archive'])),mode='r:gz') as t:tree=ast.parse(t.extractfile('tests/test_boundary.py').read())
    observed={}
    for n in ast.walk(tree):
        if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in ('versions','expected') for x in n.targets) and isinstance(n.value,ast.Dict):
            try:values=ast.literal_eval(n.value)
            except (ValueError,TypeError):continue
            observed.update({canonicalize_name(k):v for k,v in values.items()})
    assert observed['cryptography']=='46.0.3' and observed['wrapt']=='1.17.3' and observed['charset-normalizer']=='3.4.4'
    installed={canonicalize_name(r['project']):r['version'] for r in pins};available={**observed,**installed,'untokenize':'0.1.1'}
    env={'implementation_name':'cpython','implementation_version':'3.13.15','os_name':'posix','platform_machine':'aarch64','platform_python_implementation':'CPython','platform_release':'','platform_system':'Linux','platform_version':'','python_full_version':'3.13.15','python_version':'3.13','sys_platform':'linux','extra':''}
    checks=[];expanded=0
    for pin in pins:
        p=ROOT/pin['private_cache'];assert sha(p)==pin['sha256']
        with zipfile.ZipFile(p) as z:expanded+=sum(i.file_size for i in z.infolist())
        for text in pin['requires_dist']:
            req=Requirement(text)
            if req.marker and not req.marker.evaluate(env):continue
            name=canonicalize_name(req.name);assert name in available and Version(available[name]) in req.specifier,(pin['project'],text)
            checks.append({'project':pin['project'],'requirement':text,'target_version':available[name],'target_kind':'exact_upstream_source_and_publisher_metadata_copy' if name=='untokenize' else 'new_pinned_wheel' if name in installed else 'version_observed_in_completed_boundary_probe'})
    result={'pins':pins,'source_support':source,'selected_added_requirements_closed':True,'checks':checks,'target_marker_environment':env,'inherited_version_observations':{'manifest':str((prior/'completion-audit.json').relative_to(ROOT)),'sha256':sha(prior/'completion-audit.json'),'scope':'Only version assertions actually exercised by the completed boundary probe;not an entire inherited inventory.'},'compressed_wheel_bytes':sum(p['size_bytes'] for p in pins),'unpacked_wheel_member_bytes':expanded,'upstream_source_copy_bytes':source['module_bytes']+license.stat().st_size+metadata.stat().st_size,'native_wheels':[p['filename'] for p in pins if not any(tag.endswith('-any') for tag in p['wheel_tags'])],'pip_dependency_resolution_or_external_execution':False,'whole_image_compatibility':'UNVERIFIED until exact build/probes approved'}
    (HERE/'runtime-support-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'wheels':len(pins),'native':result['native_wheels'],'requirements_checked':len(checks),'source_copy':'untokenize0.1.1 with exact publisher metadata','compressed_bytes':result['compressed_wheel_bytes'],'expanded_bytes':expanded,'executed':False}))

if __name__=='__main__':main()
