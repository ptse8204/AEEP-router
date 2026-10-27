"""Current-source private installation and offline CLI journey; exact approval required."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from aeep_toolkit.install_runtime import RuntimeInstallation, apply, digest, file_digest, remove

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-reviewed-digest');args=parser.parse_args()
    review=json.loads((HERE/'operation-review.json').read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==review['driver_sha256']
    plan=RuntimeInstallation.model_validate_json((HERE/'installation.json').read_text())
    assert digest(plan)==review['installation_sha256']
    for wheel in plan.wheels:
        target=Path(plan.wheelhouse)/wheel.filename
        assert not target.exists() or file_digest(target)==wheel.sha256
    for name,sha in review['inputs'].items():assert file_digest(ROOT/name)==sha
    if args.execute_reviewed_digest is None:
        print(json.dumps({'review_sha256':digest(review),'execution':False,'wheels':len(plan.wheels)}));return
    assert args.execute_reviewed_digest==digest(review)
    approval=json.loads((HERE/'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256']==file_digest(HERE/'operation-review.json')
    assert shutil.disk_usage(ROOT).free>51*1024**3
    with (HERE/'execution-started.json').open('x') as marker:
        json.dump({'review_sha256':approval['review_sha256'],'automatic_retry':False},marker)
    downloaded=0
    for wheel in plan.wheels:
        target=Path(plan.wheelhouse)/wheel.filename
        assert target.is_file() and not target.is_symlink() and file_digest(target)==wheel.sha256, 'Exact offline wheel missing or changed; no network fallback.'
    output=HERE/'execution';output.mkdir(mode=0o700)
    checks=[]
    def save(): (output/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    start=time.monotonic();state=apply(plan,digest(plan))
    checks.append({'operation':'apply','seconds':time.monotonic()-start,'state':state});save()
    assert state['status']=='installed'
    runtime=Path(plan.destination)
    with tempfile.TemporaryDirectory(prefix='aeep-installed-cli-',dir=plan.wheelhouse) as temp:
        home=Path(temp).resolve()
        fixture_root=home/'inputs'
        for name in review['inputs']:
            target=fixture_root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        for name in ('registry.json','policy.json'):shutil.copyfile(HERE/name,home/name)
        env={'PATH':os.defpath,'HOME':str(home),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','PIP_CONFIG_FILE':os.devnull,'LC_ALL':'C'}
        profile=home/'cli.sb'
        profile.write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
            +f'(allow file-write* (subpath {json.dumps(str(home))}))\n(allow file-write* (literal "/dev/null"))\n'
            +f'(deny file-read* (subpath {json.dumps(str(Path.home().resolve()))}))\n'
            +f'(allow file-read* (subpath {json.dumps(str(runtime))}))\n')
        prefix=['/usr/bin/sandbox-exec','-f',str(profile),str(runtime/'bin/python'),'-I','-B']
        (home/'catalog.json').write_text(json.dumps({'candidates':[{'registry_candidate_id':'csv-helper','name':'CSV helper','description':'synthetic','package_locator':{'kind':'https','value':'https://example.invalid/candidate.zip'}}]}))
        (home/'discovery.json').write_text(json.dumps({'sources':[{'source_id':'local','kind':'fixture','path':'catalog.json'}]}))
        evidence=fixture_root/'reports/toolkit-v2/c06/verified-journey/result/toolkit-evidence.json'
        cases=json.loads((fixture_root/review['suite_cases']).read_text())
        for case in cases:
            for asset in (case['truth']['source'],case['truth']['tests'],case['reference'],*case['truth']['wheels']):
                asset['path']=str(fixture_root/Path(asset['path']).relative_to(ROOT))
        local_cases=home/'suite-cases.json';local_cases.write_text(json.dumps(cases))
        commands=[('repository-suite-recipe',['repository-suite-recipe','--cases',str(local_cases)]),('help',['--help']),('list',['list','full']),('candidate',['candidate',str(fixture_root/'examples/toolkit_offline/format-json')]),
            ('plan',['plan','essentials','--registry',str(home/'registry.json'),'--policy',str(home/'policy.json'),'--select','aeep-agent-router']),
            *[(f'report-{f}',['report','--evidence',str(evidence),'--format',f]) for f in ('json','markdown','html')],
            ('scripted-help',['eval','scripted','--help']),('managed-help',['eval','managed','--help']),
            ('portable',['export-preview','--evidence',str(evidence)]),
            ('trace',['trace-preview','--receipt',str(fixture_root/'reports/toolkit-v2/integration-completion/waza-review-v4/execution/receipt.json')]),
            ('import-waza',['import-report','waza','--input',str(fixture_root/'reports/toolkit-v2/integration-completion/waza-review-v4/execution/results.json'),'--revision','e534d149d89ae77ea158469fb4d2003804b2ee76','--candidate-sha256','a'*64]),
            ('repository-recipe',['repository-recipe','--cases',str(fixture_root/'examples/repository_evaluation/development-cases.json')]),
            ('selection-report',['selection-report','--evaluation',str(fixture_root/'reports/toolkit-v2/c13/repository-value-20261021/selection-software-fixture.json')]),
            ('doctor',['doctor','--host','codex','--project',str(home)]),
            ('discovery',['discover','--config',str(home/'discovery.json'),'--store',str(home/'discovery.sqlite3'),'--source','local','--query','CSV'])]
        for label,arguments in commands:
            start=time.monotonic()
            p=subprocess.run([*prefix,'-m','aeep_toolkit',*arguments],cwd=home,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
            if label=='repository-suite-recipe' and p.returncode==0:
                exported=json.loads(p.stdout)
                assert exported['extension']['schema_version']=='assessment.recipe-extension.v5'
                assert exported['generator_config']['declared_origin_counts']=={'upstream_issue':3}
                assert exported['generator_config']['assessment'] is False
                explicit=[case for case in exported['generator_config']['cases'] if case['schema_version']=='assessment.repository-suite-case.v5']
                assert len(explicit)==3 and all(c['truth']['patch_encoding']=='gzip-json' and c['truth']['pytest_plugins']==['pytest_mock','_hypothesis_pytestplugin'] and c['truth']['test_roots']==['tests'] and c['truth']['archive_profile']=='repository-v1' for c in explicit)
                assert 'patch_gzip_b64' in json.dumps(exported['output_schema'])
                summary={'export_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'case_count':3,'schema_version':exported['extension']['schema_version'],'executed_external_source':False,'raw_export_retained':False}
                (output/f'{label}.stdout').write_text(json.dumps(summary,indent=2)+'\n')
            else:
                (output/f'{label}.stdout').write_text(p.stdout)
            (output/f'{label}.stderr').write_text(p.stderr)
            checks.append({'operation':label,'returncode':p.returncode,'seconds':time.monotonic()-start});save()
            assert p.returncode==0,label
            if label=='report-json':assert json.loads(p.stdout)['outcome']=='NOT_ASSESSED'
            if label=='plan':assert json.loads(p.stdout)['execution_authorized'] is False
            if label=='discovery':assert json.loads(p.stdout)['candidate_ids']==['csv-helper']
            if label=='repository-recipe':assert json.loads(p.stdout)['extension']['schema_version']=='assessment.recipe-extension.v4'
            if label=='selection-report':assert json.loads(p.stdout)['outcome']=='NOT_ASSESSED' and json.loads(p.stdout)['evidence_kind']=='synthetic'
            if label=='trace':assert json.loads(p.stdout)['export_performed'] is False
        (home/'package-review.json').write_text(json.dumps(review))
        code='''import hashlib,json,sys
from pathlib import Path
from aeep_toolkit.cli import main
main(['list','essentials'])
assert 'aeep.router' not in sys.modules
from aeep.assessment import verification
value=verification.verification_source_digest(Path(verification.__file__).resolve().parents[3])
assert len(value)==64 and value!=hashlib.sha256().hexdigest()
print(json.dumps({'installed_source_digest':value,'router_imported':False}))
import sysconfig
import aeep.assessment.repository_suites as suites
review=json.load(open(sys.argv[1]))
assert hashlib.sha256(Path(suites.__file__).read_bytes()).hexdigest()==review['installed_module_sha256']
import importlib
for name,sha in review['installed_module_hashes'].items():
    assert hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest()==sha
schema=Path(sysconfig.get_path('data'))/'share/aeep/schemas/assessment-repository-suite-case.schema.json'
assert hashlib.sha256(schema.read_bytes()).hexdigest()==review['installed_schema_sha256']
# Exercise the installed entrypoint,including its default refusal,with only a
# first-party standard-library child. This is framing evidence,not containment.
import subprocess
from aeep.models import ActionRequest,ExecutorSpec,ExecutorKind
spec=ExecutorSpec(id='installed-frame',capability='test.frame',kind=ExecutorKind.COMMAND,description='first-party framing fixture',config={'argv':[sys.executable,'-I','-B','-c','import json,sys;v=json.load(sys.stdin);print(json.dumps({"bytes":len(v["data"])}))'],'stdin_json':True,'max_stdin_bytes':7000000,'output':{'type':'json'}})
request=ActionRequest(capability='test.frame',input={'data':'x'*2100000})
payload=json.dumps({'spec':spec.model_dump(mode='json'),'request':request.model_dump(mode='json'),'attempt':1,'approved_side_effect':'read'}).encode()
command=[sys.executable,'-I','-B','-m','aeep.assessment.container_worker']
positive=subprocess.run([*command,'--input-limit','8000000'],input=payload,capture_output=True,timeout=20)
assert positive.returncode==0 and json.loads(positive.stdout)['output']=={'bytes':2100000}
negative=subprocess.run(command,input=payload,capture_output=True,timeout=20)
assert negative.returncode!=0 and not negative.stdout
print(json.dumps({'installed_worker_frame_bytes':len(payload),'explicit_limit_passed':True,'default_limit_denied':True,'fixture_only':True}))

from aeep.errors import ConfigurationError
fixture=suites.pack_files({'library/fixture.py':b'# first-party fixture', 'public.bin':b'x'*4000001},large=True)
assert len(suites.archive_files(fixture,large=True)['public.bin'])==4000001
try:
    suites.archive_files(fixture)
except ConfigurationError as exc:
    assert "archive" in str(exc)
else:
    raise AssertionError('Compact profile accepted the expanded fixture')
assets=Path(sysconfig.get_path('data'))/'share/aeep/integrations/assessment-runtime'
for name,sha in review['installed_asset_hashes'].items():
    assert hashlib.sha256((assets/name).read_bytes()).hexdigest()==sha
print(json.dumps({'installed_suite_assets':len(review['installed_asset_hashes']),'bytes_verified':True}))
case=json.loads((Path(sys.argv[1]).parent/'suite-cases.json').read_text())[0]
truth=suites.SuiteTruthV5.model_validate(case['truth'])
assert truth.test_roots==['tests'] and truth.archive_profile=='repository-v1'
from aeep.assessment.repository_tasks import RepositoryPatch
patch=RepositoryPatch(base_sha256=truth.input_sha256,files={case['input']['editable_paths'][0]:'# first-party fixture\\n'*30000})
assert len(patch.model_dump_json().encode())>500000
encoded=suites.compressed_patch_artifact(patch)
assert suites._decode_suite_patch(truth,encoded)==patch
try:
    suites.decode_patch(encoded)
except ValueError:
    pass
else:
    raise AssertionError('Legacy format accepted v3 transport')
print(json.dumps({'compact_transport_verified':True,'fixture_only':True,'new_external_code_executed':False}))
'''
        p=subprocess.run([*prefix,'-c',code,str(home/'package-review.json')],cwd=home,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
        (output/'installed-identity.stdout').write_text(p.stdout);(output/'installed-identity.stderr').write_text(p.stderr)
        checks.append({'operation':'installed-source-identity-and-no-router','returncode':p.returncode});save();assert p.returncode==0
        capture_file=fixture_root/review['capture_fixture']
        code='''import json,sys
from aeep.models import ExecutionReceipt
from aeep_toolkit.telemetry import bound_journal,token_capture
from aeep.assessment.reporting import resource_measurements
value=json.load(open(sys.argv[1]))
receipt=ExecutionReceipt.model_validate(value['receipt'])
check=token_capture(receipt,bound_journal(receipt,value['journal']))
assert check['status']=='verified'
assert check['provider_usage_independently_verified'] is False
assert check['source']=='provider_report' and check['trust']=='self_asserted'
assert resource_measurements(receipt.accounting,receipt.actual_resources)['model.openai.gpt-6-astra.subscription.input_tokens'] is None
print(json.dumps(check))
'''
        p=subprocess.run([*prefix,'-c',code,str(capture_file)],cwd=home,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
        (output/'token-capture.stdout').write_text(p.stdout);(output/'token-capture.stderr').write_text(p.stderr)
        checks.append({'operation':'installed-token-capture-chain','returncode':p.returncode});save();assert p.returncode==0
    state=remove(plan,digest(plan));checks.append({'operation':'remove','state':state});save()
    assert state['status']=='removed' and not runtime.exists()
    (output/'summary.json').write_text(json.dumps({'source_commit':review['source_commit'],'installed_cli_checks':18,'installed_capture_checks':1,'dependency_downloaded_bytes':downloaded,'runtime_removed':True,'private_scratch_removed':not home.exists(),'model_calls':0,'qualification':False},indent=2)+'\n')
    print('Installed offline CLI journey and unchanged removal passed.')


if __name__=='__main__':main()
