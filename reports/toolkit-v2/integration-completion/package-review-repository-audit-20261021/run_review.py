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
        commands=[('help',['--help']),('list',['list','full']),('candidate',['candidate',str(fixture_root/'examples/toolkit_offline/format-json')]),
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
            (output/f'{label}.stdout').write_text(p.stdout);(output/f'{label}.stderr').write_text(p.stderr)
            checks.append({'operation':label,'returncode':p.returncode,'seconds':time.monotonic()-start});save()
            assert p.returncode==0,label
            if label=='report-json':assert json.loads(p.stdout)['outcome']=='NOT_ASSESSED'
            if label=='plan':assert json.loads(p.stdout)['execution_authorized'] is False
            if label=='discovery':assert json.loads(p.stdout)['candidate_ids']==['csv-helper']
            if label=='repository-recipe':assert json.loads(p.stdout)['extension']['schema_version']=='assessment.recipe-extension.v4'
            if label=='selection-report':assert json.loads(p.stdout)['outcome']=='NOT_ASSESSED' and json.loads(p.stdout)['evidence_kind']=='synthetic'
            if label=='trace':assert json.loads(p.stdout)['export_performed'] is False
        code='''import hashlib,json,sys
from pathlib import Path
from aeep_toolkit.cli import main
main(['list','essentials'])
assert 'aeep.router' not in sys.modules
from aeep.assessment import verification
value=verification.verification_source_digest(Path(verification.__file__).resolve().parents[3])
assert len(value)==64 and value!=hashlib.sha256().hexdigest()
print(json.dumps({'installed_source_digest':value,'router_imported':False}))
'''
        p=subprocess.run([*prefix,'-c',code],cwd=home,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
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
    (output/'summary.json').write_text(json.dumps({'source_commit':review['source_commit'],'installed_cli_checks':17,'installed_capture_checks':1,'dependency_downloaded_bytes':downloaded,'runtime_removed':True,'private_scratch_removed':not home.exists(),'model_calls':0,'qualification':False},indent=2)+'\n')
    print('Installed offline CLI journey and unchanged removal passed.')


if __name__=='__main__':main()
