"""Freeze four semantic multi-file subjects and a private image context as data."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

from aeep.assessment.repository_suites import pack_files
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-worker-input-20261027'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def main():
    stable=json.loads((OLD/'validation/source-stability.json').read_text());assert stable['all_passed'] and verification_source_digest(ROOT)==stable['source_digest']
    assert json.loads((OLD/'bundle-execution-result.json').read_text())['all_components_passed']
    raw=json.loads((HERE/'prepared-cases.json').read_text());wanted={'canopen-python__canopen-613','duo-labs__py_webauthn-241','tefra__xsdata-1126','tefra__xsdata-1132'}
    descriptions=[x for x in raw['cases'] if x['original_issue_id'] in wanted];assert len(descriptions)==4
    ids={x['id'] for x in descriptions};cases=[x for x in json.loads((ROOT/raw['cases_file']).read_text()) if x['input']['task_id'] in ids];variants=[x for x in json.loads((ROOT/raw['variants_file']).read_text()) if x['case'] in ids];assert len(cases)==4 and len(variants)==16
    directory=ROOT/'.aeep/repository-multifile-execution-cases-20261027';directory.mkdir(exist_ok=False)
    save(directory/'cases.json',cases);save(directory/'variants.json',variants)
    meta={**raw,'cases_file':str((directory/'cases.json').relative_to(ROOT)),'cases_file_sha256':sha(directory/'cases.json'),'variants_file':str((directory/'variants.json').relative_to(ROOT)),'cases':descriptions,'prepared_cases':4,'payloads':16,'errors':[],'unselected_preparation_errors_retained_in':'prepared-cases.json'};save(HERE/'execution-cases.json',meta)
    save(HERE/'curation-dispositions.json',{'selected_ids':sorted(ids),'selected_cases':4,'selected_family':'multi-file-repair','required_identities':sum(x['required_tests'] for x in descriptions),'pymdown_excluded_from_multifile':['2576','2807'],'pymdown_reason':'The second changed file is only a version constant in __meta__.py;one functional file is insufficient for this family. Initial inert records remain.','pyinfra_deferred':'src-layout project entrypoints/dynamic metadata plus gevent/paramiko runtime need a separate reviewed project profile;not included in this minimal dependency image.','other_preparation_exclusions':raw['errors'],'source_guard_exclusions':'See source-size-review.json:two prohibited member/path trees and one partial over-cap archive.','new_subject_execution':False})
    closure=json.loads((HERE/'runtime-support-review.json').read_text());context=ROOT/'.aeep/repository-multifile-image-20261027';context.mkdir(exist_ok=False)
    for pin in closure['pins']:
        source=ROOT/pin['private_cache'];assert sha(source)==pin['sha256'];shutil.copyfile(source,context/pin['filename'])
    source=closure['source_support'];support=context/'untokenize-support';support.mkdir();(support/'untokenize-0.1.1.dist-info').mkdir()
    shutil.copyfile(ROOT/source['module_cache'],support/'untokenize.py');shutil.copyfile(ROOT/source['licenses'][0]['path'],support/'LICENSE.untokenize.source');shutil.copyfile(ROOT/source['publisher_metadata_path'],support/'untokenize-0.1.1.dist-info/METADATA')
    assert sha(support/'untokenize.py')==source['module_sha256'] and sha(support/'untokenize-0.1.1.dist-info/METADATA')==source['publisher_metadata_sha256']
    (context/'requirements.txt').write_text(''.join('/opt/aeep-runtime/'+p['filename']+' --hash=sha256:'+p['sha256']+'\n' for p in closure['pins']))
    parent='aeep-toolkit-v2/repository-grader:py313-large-repositories-20261027'
    dockerfile='FROM '+parent+'\nUSER 0:0\nCOPY '+' '.join(p['filename'] for p in closure['pins'])+' requirements.txt /opt/aeep-runtime/\nRUN ["python3", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", "--disable-pip-version-check", "--require-hashes", "-r", "/opt/aeep-runtime/requirements.txt"]\nCOPY untokenize-support/ /usr/local/lib/python3.13/site-packages/\nUSER 65534:65534\n';(context/'Dockerfile').write_text(dockerfile)
    for path in context.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
    old_review=json.loads((OLD/'operation-review.json').read_text());parent_review=json.loads((ROOT/old_review['parent_review']).read_text());parent_review['source_digest']=stable['source_digest'];parent_review['external_execution']=False
    canary=str((directory/'host-canary').relative_to(ROOT));prior_canary=parent_review['host_canary'];parent_review['host_canary']=canary
    versions={p['project']:p['version'] for p in closure['pins']};versions['untokenize']='0.1.1'
    test='\n\ndef test_new_multifile_supports():\n    import importlib.metadata,hashlib,io,tokenize\n    from pathlib import Path\n    import can,canmatrix,asn1crypto,cbor2,OpenSSL,lxml,docformatter,untokenize,toposort\n    from asn1crypto import core\n    from lxml import etree\n    expected='+repr(versions)+'\n    for name,version in expected.items():\n        dist=importlib.metadata.distribution(name)\n        assert dist.version==version\n        assert str(dist.locate_file(""))=="/usr/local/lib/python3.13/site-packages"\n    for module in (can,canmatrix,asn1crypto,cbor2,OpenSSL,lxml,docformatter,untokenize,toposort):\n        assert Path(module.__file__).is_relative_to("/usr/local/lib/python3.13/site-packages")\n    assert hashlib.sha256(Path(untokenize.__file__).read_bytes()).hexdigest()=='+repr(source['module_sha256'])+'\n    assert hashlib.sha256((Path(untokenize.__file__).parent/"untokenize-0.1.1.dist-info/METADATA").read_bytes()).hexdigest()=='+repr(source['publisher_metadata_sha256'])+'\n    assert can.Message(arbitration_id=1,data=b"ok").arbitration_id==1\n    assert not canmatrix.CanMatrix().frames\n    assert core.Integer(1).dump()==b"\\x02\\x01\\x01"\n    assert cbor2.loads(cbor2.dumps({"number":1}))=={"number":1}\n    assert OpenSSL.SSL.Context(OpenSSL.SSL.TLS_METHOD) is not None\n    assert etree.fromstring(b"<root/>").tag=="root"\n    value="x = 1\\n"\n    assert untokenize.untokenize(tokenize.generate_tokens(io.StringIO(value).readline))==value\n    assert toposort.toposort_flatten({"one":set()})==["one"]\n'
    for probe in parent_review['probes']:
        payload=probe['payload']
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(payload['archive'])),mode='r:gz') as archive:files={m.name:archive.extractfile(m).read() for m in archive if m.isfile()}
        files={name:body.replace(prior_canary.encode(),canary.encode()) for name,body in files.items()}
        if probe['name']=='boundary':files['tests/test_boundary.py']+=test.encode()
        encoded=pack_files(files,large=True);payload['archive']=base64.b64encode(encoded).decode();payload['archive_sha256']=hashlib.sha256(encoded).hexdigest();probe['archive_sha256']=payload['archive_sha256'];probe['payload_sha256']=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
    save(HERE/'observer-envelope.json',parent_review)
    out=HERE/'runtime-execution';out.mkdir()
    for name in ('run.py','audit-execution.py','classify.py','operator_output.py'):
        text=(OLD/name).read_text().replace('ROOT = HERE.parents[3]','ROOT = HERE.parents[4]')
        if name=='run.py':
            text=text.replace("HERE / 'review-budget.py'", "HERE.parent / 'review-budget.py'").replace('envelope = review',"envelope = json.loads((HERE.parent / 'runtime-review.json').read_text())").replace("json.loads((HERE / 'review-budget-anchor.json').read_text())['grant_before']","json.loads((HERE.parent / 'build-result.json').read_text())['grant_before']")
        (out/name).write_text(text)
    shutil.copyfile(OLD/'review-budget.py',HERE/'review-budget.py')
    template=HERE.parent/'repository-effective-runtime-20261027'
    text=(template/'run-bundle.py').read_text().replace("len(parent['RootFS']['Layers']) + 2", "len(parent['RootFS']['Layers']) + 3");(HERE/'run-bundle.py').write_text(text)
    text=(template/'derive-execution.py').read_text().replace('repository-effective-runtime-20261027','repository-multifile-runtime-20261027').replace('Six provisional tasks and three fresh runtime probes','Four multi-file tasks and four fresh runtime probes').replace('nineteen offline calls','twenty-four offline calls')
    (HERE/'derive-execution.py').write_text(text)
    print(json.dumps({'cases':len(cases),'variants':len(variants),'required_identities':sum(x['required_tests'] for x in descriptions),'new_cached_wheels':len(closure['pins']),'upstream_module_and_publisher_metadata_copy':'untokenize0.1.1','new_filesystem_layers':3,'actual_builds_tests_or_installs':0}))

if __name__=='__main__':main()
