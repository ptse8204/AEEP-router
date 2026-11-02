"""One isolated continuation for the unchanged SDK; two locale-stable docs attempts."""
from __future__ import annotations
import argparse,asyncio,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
FROZEN=ROOT/'.aeep/stack-frozen-source-443b90a7'
sys.path.insert(0,str(FROZEN/'src'))
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,SideEffect,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest,snapshot


def tools_state(runtime):
    files={}
    for directory in ('bin','node_modules'):
        for path in (runtime/directory).rglob('*'):
            if path.is_file():files[str(path.relative_to(runtime))]=file_digest(path)
    for name in ('operation.json','profile.sb'):files[name]=file_digest(runtime/name)
    return files


def verify():
    review=json.loads((HERE/'operation-review.json').read_text())
    for name,value in review['bound_files'].items():assert file_digest(ROOT/name)==value,name
    assert verification_source_digest(FROZEN)==review['checkout_source']
    assert snapshot(Path(review['sdk_runtime']))==review['sdk_runtime_snapshot']
    state=json.loads(Path(review['docs_runtime_record']).read_text())
    assert state['runtime']==review['docs_runtime']
    assert tools_state(Path(state['runtime']))==state['files']
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}
    lines=subprocess.run(['/usr/bin/make','-n','docs-check'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=10,check=True).stdout.splitlines()
    import shlex
    assert shlex.split(lines[0])==['npx','--yes','markdownlint-cli2@0.23.3','--config','.markdownlint-cli2.jsonc','--no-globs',*review['documents']]
    return review


async def framework(review,identity):
    with (HERE/'framework-started.json').open('x') as stream:json.dump({'review_sha256':identity},stream)
    old=ROOT/review['sdk_parent']
    working=old/'execution/owned-work/agent-framework-continuation-20261102'
    working.mkdir(mode=0o700)
    for name in ('home','tmp'):(working/name).mkdir(mode=0o700)
    worker=working/'functional-check.py';worker.write_bytes((old/'functional-check.py').read_bytes())
    assert file_digest(worker)==review['sdk_worker_sha256']
    profile=HERE/'framework-boundary.sb';runtime=Path(review['sdk_runtime'])
    spec=ExecutorSpec(id='toolkit.agent-framework-continuation',capability='toolkit.upstream-engineering@1',kind='command',side_effect='write',
      config={'argv':['/usr/bin/sandbox-exec','-f',str(profile),str(runtime/'bin/python'),'-I','-B',str(worker)],
       'argv_literal':True,'inherit_env':False,'stdin_json':True,'cwd':str(working),'timeout_seconds':90,'max_output_bytes':1048576,'output':{'type':'json'},
       'env':{'PATH':'/usr/bin:/bin','HOME':str(working/'home'),'TMPDIR':str(working/'tmp'),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}})
    action=ActionRequest(capability=spec.capability,input={'review_sha256':identity,'installed_source':review['installed_source'],'canary_path':str(old/'functional-check.py')})
    context=ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,approved_side_effect=SideEffect.WRITE)
    executor=CommandExecutor();began=utc_now();raw=None
    try:raw=await (await executor.start(context)).task
    finally:await executor.close()
    receipt=ExecutionReceipt(decision_id='reviewed-framework-continuation',action_id=action.action_id,capability=spec.capability,
     executor_id=spec.id,executor_kind=spec.kind,status=raw.status,started_at=began,ended_at=utc_now(),estimated=spec.estimate,
     actual_resources=raw.resources,accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,
     metadata={'review_sha256':identity,'evidence_kind':'upstream_engineering',**raw.metadata})
    store=ReceiptStore(HERE/'outer-receipts.sqlite3')
    try:store.save_receipt(receipt)
    finally:store.close()
    (HERE/'framework-receipt.json').write_text(receipt.model_dump_json(indent=2)+'\n')
    (HERE/'framework-process.json').write_text(json.dumps({'stdout':(raw.stdout or '')[:8192],'stderr':(raw.stderr or '')[:8192]},indent=2)+'\n')
    result={'passed':False,'receipt_id':receipt.receipt_id,'runtime_retained':True,'models':0,'owned_work':str(working)}
    if isinstance(raw.output,dict):
        (HERE/'framework-result.json').write_text(json.dumps(raw.output,indent=2)+'\n')
        result['passed']=(receipt.execution_success is True and raw.output.get('operations')==5 and raw.output.get('models')==0
            and len(raw.output.get('checks',[]))==5 and all(check.get('passed') is True for check in raw.output['checks']))
    result['runtime_unchanged']=snapshot(runtime)==review['sdk_runtime_snapshot']
    assert result['runtime_unchanged']
    (HERE/'framework-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def docs(review,identity):
    runtime=Path(review['docs_runtime']);state=json.loads(Path(review['docs_runtime_record']).read_text())
    existing=sorted(HERE.glob('docs-attempt-*.json'));assert len(existing)<2 and not (HERE/'docs-complete.json').exists()
    attempt=2+len(existing)
    record={'review_sha256':identity,'attempt':attempt,'parent_attempt':review['docs_parent']+'/attempt-1.json',
     'models':0,'network':False,'outer_make_locale':'C','tools_unchanged':False,
     'input_hashes':{name:file_digest(ROOT/name) for name in review['documents']}}
    path=HERE/f'docs-attempt-{attempt}.json'
    with path.open('x') as stream:json.dump(record,stream,indent=2)
    started=time.monotonic()
    try:
        env={'PATH':str(runtime/'bin')+':/usr/local/bin:/usr/bin:/bin','HOME':str(runtime/'home'),'TMPDIR':str(runtime/'tmp'),'LC_ALL':'C'}
        with (HERE/f'docs-attempt-{attempt}.log').open('x') as log:
            completed=subprocess.run(['/usr/bin/make','docs-check','LYCHEE='+str(runtime/'bin/lychee-sandbox')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        record.update(passed=completed.returncode==0,returncode=completed.returncode)
        record['tools_unchanged']=tools_state(runtime)==state['files'];assert record['tools_unchanged']
        assert all(file_digest(ROOT/name)==value for name,value in record['input_hashes'].items())
    except BaseException as error:record.update(passed=False,error_type=type(error).__name__)
    finally:
        record['wall_seconds']=time.monotonic()-started;path.write_text(json.dumps(record,indent=2)+'\n')
        if record.get('passed'):(HERE/'docs-complete.json').write_text(json.dumps({'review_sha256':identity,'attempt':attempt})+'\n')
    return {key:value for key,value in record.items() if key!='input_hashes'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');parser.add_argument('--component',choices=['both','framework','docs'],default='both');args=parser.parse_args()
    review=verify();identity=file_digest(HERE/'operation-review.json')
    if args.execute_approved is None:
        print(json.dumps({'review_sha256':identity,'executed':False,'runtime_created':False}));return
    assert args.execute_approved==identity and not (HERE/'withdrawn.json').exists()
    approval=json.loads((HERE/'operator-approval.json').read_text());assert approval['approved'] is True and approval['review_sha256']==identity
    assert shutil.disk_usage(ROOT).free>50*1024**3+32*1024**2
    results={}
    if args.component in ('both','framework'):
        try:results['framework']=asyncio.run(framework(review,identity))
        except BaseException as error:results['framework']={'passed':False,'error_type':type(error).__name__}
    if args.component in ('both','docs'):results['docs']=docs(review,identity)
    with (HERE/f'run-{time.time_ns()}.json').open('x') as stream:json.dump(results,stream,indent=2)
    print(json.dumps(results))


if __name__=='__main__':main()
