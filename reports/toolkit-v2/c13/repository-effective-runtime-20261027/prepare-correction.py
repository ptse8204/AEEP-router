"""Prepare the effective runtime and explicit pytest-row adapter as inert data."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment,RecipeMaterializationRequest,content_digest
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'repository-test-roots-20261027'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def pack(files):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            item=tarfile.TarInfo(name);item.mode=0o444;item.size=len(data);archive.addfile(item,io.BytesIO(data))
    return out.getvalue()


def main():
    assert verification_source_digest(ROOT)==json.loads((OLD/'validation/source-stability.json').read_text())['source_digest']
    audit=json.loads((OLD/'runtime-execution/completion-audit.json').read_text())
    previous=json.loads((OLD/'runtime-execution/parent-runtime-review.json').read_text())
    assert audit['batch_completed'] and audit['all_owned_containers_absent']
    out=HERE/'runtime-execution';out.mkdir(exist_ok=False)
    for name in ('review-budget.py','run-bundle.py','derive-execution.py','runtime-execution/run.py','runtime-execution/audit-execution.py','runtime-execution/classify.py','runtime-execution/operator_output.py'):
        shutil.copyfile(OLD/name,HERE/name)
    s=(HERE/'run-bundle.py').read_text().replace("len(parent['RootFS']['Layers']) + 3","len(parent['RootFS']['Layers']) + 2")
    (HERE/'run-bundle.py').write_text(s)
    s=(HERE/'derive-execution.py').read_text().replace('repository-rooted-runtime-20261027','repository-effective-runtime-20261027').replace('Eight provisional tasks','Six provisional tasks').replace('twenty-three offline calls','nineteen offline calls')
    (HERE/'derive-execution.py').write_text(s)
    source=(OLD/'operator-observer.py').read_text()
    old="        statuses = parse_log_pytest(log.read_text(errors='replace'), None)"
    new="""        # Frame pytest result rows before the pinned upstream parser. Application
        # logging prefixes are not test statuses; preserve real module errors too.
        lines = log.read_text(errors='replace').splitlines()
        framed = [line for line in lines if re.match(
            r'^(?:PASSED|FAILED|ERROR|SKIPPED|XFAIL)\\s+[^\\s]+\\.py(?:::|\\s|$)', line)]
        statuses = parse_log_pytest('\\n'.join(framed), None)"""
    assert source.count(old)==1;source=source.replace(old,new)
    (HERE/'operator-observer.py').write_text(source)
    save(HERE/'operator-observer-review.json',{'stock_parser_body_unchanged':source.startswith((ROOT/'integrations/assessment-runtime/swe_rebench_pytest_parser.py').read_text()+'\n'),'previous_operator_program_sha256':sha(OLD/'operator-observer.py'),'operator_program_sha256':sha(HERE/'operator-observer.py'),'change':'Frame only exact whitespace-delimited pytest status tokens followed by a Python module test identity before the unchanged upstream parser. Preserve real collection errors and every test-row identity; protected grading is unchanged.','public_failure_tail_limit_bytes':8192,'product_default_observer_unchanged':True,'execution_started':False,'limitations':['Not adversarial log-forgery protection. The parser still cannot establish unsupported whitespace-containing identities; missing identities remain failures.','The prior successful SQL552 log stream was not retained. New synthetic fixtures cannot reconstruct it or convert the old rejected attempt into a pass.']})
    # Build inputs come only from three existing cached wheels; metadata is not
    # evidence that a distribution has already been installed in an image.
    support_source=HERE.parent/'repository-workload-batch-20261022/runtime-support-review.json'
    support=json.loads(support_source.read_text());pins=[p for p in support['pins'] if p['project'] in ('python-dateutil','six','tzdata')];assert len(pins)==3
    for pin in pins:
        assert sha(ROOT/pin['private_cache'])==pin['sha256']
        for license in pin['licenses']:assert sha(ROOT/license['retained'])==license['sha256']
    save(HERE/'runtime-support-review.json',{'pins':pins,'downloaded_wheel_bytes':sum((ROOT/p['private_cache']).stat().st_size for p in pins),'selected_added_requirements_closed':True,'entire_inherited_runtime_closure':'NOT_CLAIMED; previous manifest mixed image and portable pins','provenance_manifest':str(support_source.relative_to(ROOT)),'provenance_manifest_sha256':sha(support_source),'planned_installs':3,'actual_installs':0,'downloads':0,'execution_started':False,'effective_probe_wheels':'Only four exact pytest bootstrap wheels; dateutil, six, freezegun and all optional supports must resolve from the image during fresh probes.'})
    # Keep the same source/test/artifact payloads; select only the six exclusions.
    meta=json.loads((OLD/'execution-cases.json').read_text());ids=set(meta['cases'][i]['id'] for i in range(len(meta['cases'])))-set(audit['eligible_cases'])
    cases=[c for c in json.loads((ROOT/meta['cases_file']).read_text()) if c['input']['task_id'] in ids]
    variants=[v for v in json.loads((ROOT/meta['variants_file']).read_text()) if v['case'] in ids]
    data=ROOT/'.aeep/repository-effective-runtime-20261027';data.mkdir(exist_ok=False)
    save(data/'cases.json',cases);save(data/'variants.json',variants)
    save(HERE/'execution-cases.json',{**meta,'prepared_cases':6,'payloads':16,'cases_file':str((data/'cases.json').relative_to(ROOT)),'cases_file_sha256':sha(data/'cases.json'),'variants_file':str((data/'variants.json').relative_to(ROOT)),'cases':[c for c in meta['cases'] if c['id'] in ids],'errors':[]})
    # New profile identity; no old conformance applies. Actual image is bound only
    # after the approved build. Do not copy the six old reservations or receipts.
    recipe=copy.deepcopy(previous['recipe'])
    for role in ('generator','reference','grader'):recipe['extension'][role]['config']['argv']=['python3','-B','-c',source]
    recipe['dependencies']['program']=sha(HERE/'operator-observer.py')
    recipe['recipe_id']='repository-effective-profile-'+content_digest(recipe)[:16]
    environment=AssessmentEnvironment.model_validate(next(x['document'] for x in previous['documents'].values() if x['kind']=='environment'))
    environment.environment_id='repository-effective-parent-20261027'
    environment.identity={'source_digest':verification_source_digest(ROOT),'purpose':'New image-installed dependency and explicit pytest-row profile; no campaign authority'}
    documents={k:v for k,v in previous['documents'].items() if v['kind']=='recipe_runtime'}
    for kind,identity,value in [('recipe',recipe['recipe_id'],recipe),('environment',environment.environment_id,environment.model_dump(mode='json'))]:documents[content_digest(value)]={'kind':kind,'id':identity,'document':value}
    request=RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',subject_digest=previous['request']['subject_digest'],recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=content_digest(environment),authorization_id='onboarding',seed=89,definition_digests=list(documents),runtime_dependencies=runtime_dependencies())
    canary='.aeep/repository-effective-runtime-20261027/host-canary';probes=copy.deepcopy(previous['probes'])
    required={'pytest','iniconfig','packaging','pluggy'}
    for probe in probes:
        p=probe['payload'];p['wheels']=[w for w in p['wheels'] if w['filename'].split('-')[0] in required];assert len(p['wheels'])==4
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(p['archive'])),mode='r:gz') as archive:files={m.name:archive.extractfile(m).read() for m in archive if m.isfile()}
        for name in files:files[name]=files[name].replace(previous['host_canary'].encode(),canary.encode())
        if probe['name']=='boundary':
            files['tests/test_boundary.py']+=b'\n\ndef test_image_installed_date_supports():\n    import importlib.metadata,dateutil,six,tzdata\n    from pathlib import Path\n    for name,version in {"python-dateutil":"2.9.0.post0","six":"1.17.0","tzdata":"2025.2"}.items():\n        dist=importlib.metadata.distribution(name)\n        assert dist.version==version\n        assert str(dist.locate_file(""))=="/usr/local/lib/python3.13/site-packages"\n    for module in (dateutil,six,tzdata):\n        assert Path(module.__file__).is_relative_to("/usr/local/lib/python3.13/site-packages")\n'
        archive=pack(files);p['archive']=base64.b64encode(archive).decode();p['archive_sha256']=hashlib.sha256(archive).hexdigest();probe['archive_sha256']=p['archive_sha256'];probe['payload_sha256']=hashlib.sha256(json.dumps(p,separators=(',',':')).encode()).hexdigest()
    save(HERE/'observer-envelope.json',{**previous,'source_digest':verification_source_digest(ROOT),'recipe':recipe,'request':request.model_dump(mode='json'),'documents':documents,'host_canary':canary,'probes':probes,'external_execution':False,'old_conformance_applies_to_new_source':False,'profile':'New explicit pytest-row framing and image-installed dependency profile; no inherited conformance'})
    print(json.dumps({'prepared_only':True,'cases':len(cases),'variants':len(variants),'new_installs':0,'source_digest':verification_source_digest(ROOT)}))


if __name__=='__main__':main()
