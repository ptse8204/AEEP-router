"""Adapt reviewed first-party drivers before binding any new execution authority."""
from pathlib import Path
import json,hashlib,base64
from aeep.assessment.repository_suites import archive_files,pack_files

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def main():
    old=HERE.parent/'repository-replacement-runtime-20261022'
    out=HERE/'runtime-execution';out.mkdir(exist_ok=False)
    for name in ('run.py','audit-execution.py','classify.py'):
        text=(HERE.parent/'repository-compact-patches-20261022'/name).read_text()
        if name!='classify.py':text=text.replace('ROOT = HERE.parents[3]','ROOT = HERE.parents[4]')
        (out/name).write_text(text)
    text=(old/'run-bundle.py').read_text().replace("timeout=1100)","timeout=json.loads((HERE / 'approval-bundle.json').read_text())['maximum_reserved_seconds'] + 60)")
    (HERE/'run-bundle.py').write_text(text)
    text=(old/'derive-execution.py').read_text().replace("'repository-explicit-plugin-runtime-20261022'","'repository-pydantic-django-runtime-20261022'")
    text=text.replace("description='Eight provisional workloads and three fresh runtime probes; no campaign or models.'","description='Twenty-two provisional tasks and three fresh runtime probes; no campaign or models.'").replace('seed=47','seed=67').replace("('run.py', 'classify.py')","('run.py', 'classify.py', 'audit-execution.py')")
    text=text.replace('maximum_operations=27, maximum_reserved_seconds=1025, maximum_contained_calls=25',"maximum_operations=bundle['maximum_operations'] - 1, maximum_reserved_seconds=bundle['maximum_reserved_seconds'] - 180, maximum_contained_calls=bundle['maximum_contained_calls']")
    text=text.replace('at most twenty-five offline calls.','at most ninety-seven offline calls.').replace("'maximum_calls': 25","'maximum_calls': bundle['maximum_contained_calls']")
    (HERE/'derive-execution.py').write_text(text)
    parent=json.loads((HERE.parent/'repository-compact-patches-20261022/parent-runtime-review.json').read_text())
    pins=json.loads((HERE/'runtime-install-review.json').read_text())['pins'];versions={p['project']:p['version'] for p in pins}
    changed=0
    for probe in parent['probes']:
        if probe['name']!='boundary':continue
        files=archive_files(base64.b64decode(probe['payload']['archive']));name=probe['expected_node'].split('::')[0]
        addition='\n\ndef test_reviewed_runtime_supports():\n    import importlib.metadata\n    expected = '+repr(versions)+'\n    for project, version in expected.items():\n        assert importlib.metadata.version(project) == version\n    import pydantic\n    import django\n    class Checked(pydantic.BaseModel):\n        number: int\n    assert Checked.model_validate({"number": "3"}).number == 3\n    assert django.get_version() == "5.2.7"\n'
        files[name]+=addition.encode();archive=pack_files(files);probe['payload']['archive']=base64.b64encode(archive).decode();probe['payload']['archive_sha256']=hashlib.sha256(archive).hexdigest();probe['archive_sha256']=probe['payload']['archive_sha256'];probe['payload_sha256']=hashlib.sha256(json.dumps(probe['payload'],separators=(',',':')).encode()).hexdigest();changed+=1
    assert changed==1 and len(parent['probes'])==3
    parent['current_probe_extension']='The boundary probe additionally verifies all14 newly installed distribution versions and basic compiled-Pydantic/Django imports. Fresh probes remain mandatory; no old conformance transfers.'
    (HERE/'observer-envelope.json').write_text(json.dumps(parent,indent=2)+'\n')
    print(json.dumps({'adapted_drivers':5,'boundary_probe_extended':True,'source_subjects_executed':0,'builds':0}))


if __name__=='__main__':main()
