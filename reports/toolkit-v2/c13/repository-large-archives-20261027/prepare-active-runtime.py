"""Defer cloud fixtures and bind the one required native math wheel without fetching it."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
meta=json.loads((HERE/'execution-cases.json').read_text());cases=json.loads((ROOT/meta['cases_file']).read_text());variants=json.loads((ROOT/meta['variants_file']).read_text())
(HERE/'all-eight-inert-cases.json').write_text(json.dumps(meta,indent=2)+'\n')
selected=[c for c in cases if 'smart_open' not in c['input']['task_id']];ids={c['input']['task_id'] for c in selected};active=[v for v in variants if v['case'] in ids]
out=ROOT/'.aeep/repository-large-selected-cases-20261027';out.mkdir(exist_ok=False)
for name,value in [('cases.json',selected),('variants.json',active)]:
    (out/name).write_text(json.dumps(value,indent=2)+'\n')
meta.update(prepared_cases=6,cases_file=str((out/'cases.json').relative_to(ROOT)),cases_file_sha256=hashlib.sha256((out/'cases.json').read_bytes()).hexdigest(),variants_file=str((out/'variants.json').relative_to(ROOT)),cases=[c for c in meta['cases'] if c['id'] in ids],payloads=12)
(HERE/'execution-cases.json').write_text(json.dumps(meta,indent=2)+'\n')
raw=(HERE/'scipy-publisher-metadata.json').read_bytes();metadata=json.loads(raw)
filename='scipy-1.15.3-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl'
entry=next(e for e in metadata['urls'] if e['filename']==filename);assert not entry['yanked'] and entry['size']==35174018
license_text=metadata['info']['license'].encode();(HERE/'scipy-publisher-license.txt').write_bytes(license_text)
plan={'project':'scipy','version':'1.15.3','filename':filename,'source_url':entry['url'],'sha256':entry['digests']['sha256'],'size_bytes':entry['size'],'metadata_url':'https://pypi.org/pypi/scipy/1.15.3/json','metadata_sha256':hashlib.sha256(raw).hexdigest(),'publisher_license_path':str((HERE/'scipy-publisher-license.txt').relative_to(ROOT)),'publisher_license_sha256':hashlib.sha256(license_text).hexdigest(),'requires_python':metadata['info']['requires_python'],'required_runtime_dependency':'numpy<2.5,>=1.23.5','inherited_numpy_version':'2.2.6','target':'CPython3.13 normal GIL Linux aarch64 manylinux2.17;not cp313t','downloaded':False,'wheel_metadata_and_license_receipt_required_before_installation':True,'maximum_download_seconds':90,'maximum_reserved_fetch_seconds':120,'maximum_download_bytes':entry['size'],'download_destinations':['files.pythonhosted.org'],'host_installation':False}
(HERE/'pending-wheel-fetch.json').write_text(json.dumps(plan,indent=2)+'\n')
(HERE/'runtime-fit-review.json').write_text(json.dumps({'active_cases':6,'active_variants':12,'active_repositories':3,'cloud_cases_deferred':['piskvorky__smart_open-889-declared-tests','piskvorky__smart_open-892-aeep-contract-audit'],'cloud_reason':'Selected tests/test_s3.py directly imports boto3,botocore,moto. Their mocked AWS runtime is outside this image review;assertions are not removed.','graph_dependency':'NetworkX7804 source imports scipy.sparse.linalg.eigsh for the declared spectral tests;exact SciPy wheel fetch/installation is proposed,not performed.','pexpect_not_added':'It occurs only in an unrelated Cyclopts completion conftest,not the selected test modules/ancestor conftest. No extra install is justified.','new_subject_or_install_execution':False},indent=2)+'\n')
print(json.dumps({'active_cases':len(selected),'variants':len(active),'scipy_bytes_pending_approval':entry['size'],'downloaded':False}))
