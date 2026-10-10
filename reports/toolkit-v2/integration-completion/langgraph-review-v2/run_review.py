"""Exact optional LangGraph installation and four no-model worker checks; inert by default."""
import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import RuntimeInstallation, apply, digest, file_digest, remove

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'integrations/toolkit'))
from stack import probe, sandbox

CASES = [({'text':'MiXeD', 'case':'upper', 'suffixes':2}, {'text':'MIXED!!', 'steps':3}, 'success'),
         ({'text':'MiXeD', 'case':'lower', 'suffixes':0}, {'text':'mixed', 'steps':1}, 'success'),
         ({'text':'', 'case':'upper', 'suffixes':3}, {'text':'!!!', 'steps':4}, 'success'),
         ({'text':'invalid', 'case':'upper', 'suffixes':4}, None, 'failed')]


async def check(plan, review):
    output=HERE/'execution';output.mkdir(mode=0o700)
    installation=apply(plan, digest(plan))
    (output/'installation.json').write_text(json.dumps(installation,indent=2)+'\n')
    runtime=Path(plan.destination)
    results=[]
    store=ReceiptStore(output/'receipts.sqlite3')
    worker=ROOT/'integrations/toolkit/langgraph_fixture.py'
    try:
        for index,(payload,expected,status) in enumerate(CASES):
            with tempfile.TemporaryDirectory(prefix='aeep-langgraph-case-') as temporary:
                working=Path(temporary).resolve()
                prefix,env=sandbox(working,runtime)
                boundary=probe(prefix,env,working)
                source=worker.read_bytes()
                assert hashlib.sha256(source).hexdigest()==review['worker_sha256']
                staged=working/'worker.py';staged.write_bytes(source)
                spec=ExecutorSpec(id='toolkit.langgraph.fixture',capability='toolkit.workflow.fixture',kind='command',
                    description='Reviewed finite LangGraph text fixture; no provider or candidate code',side_effect='write',
                    config={'argv':[*prefix,str(staged)],'argv_literal':True,'stdin_json':True,'inherit_env':False,
                            'env':env,'cwd':str(working),'timeout_seconds':30,'max_output_bytes':16384,'output':{'type':'json'}})
                action=ActionRequest(capability=spec.capability,input=payload)
                context=ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,approved_side_effect=SideEffect.WRITE)
                executor=CommandExecutor();started=utc_now()
                try:
                    raw=await (await executor.start(context)).task
                finally:
                    await executor.close()
                receipt=ExecutionReceipt(decision_id='reviewed-langgraph-'+str(index),action_id=action.action_id,
                    capability=spec.capability,executor_id=spec.id,executor_kind=spec.kind,status=raw.status,
                    started_at=started,ended_at=utc_now(),estimated=spec.estimate,actual_resources=raw.resources,
                    accounting=raw.accounting,execution_success=raw.status.value=='success',
                    metadata={'review_sha256':digest(review),'worker_sha256':review['worker_sha256'],'evidence_kind':'synthetic'},error_type=raw.error_type)
                store.save_receipt(receipt)
                passed=raw.status.value==status and (expected is None or raw.output==expected)
                results.append({'case':index,'passed':passed,'receipt_id':receipt.receipt_id,'boundary':boundary,
                                'status':raw.status.value,'expected_status':status})
                (output/'checks.json').write_text(json.dumps(results,indent=2)+'\n')
                assert passed, 'worker failed; preserve records and runtime, no automatic retry'
    finally:
        store.close()
    removed=remove(plan,digest(plan))
    (output/'removal.json').write_text(json.dumps(removed,indent=2)+'\n')
    print(json.dumps({'checks':len(results),'passed':all(row['passed'] for row in results),'model_calls':0,'live_qualification':False}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-reviewed-digest');args=parser.parse_args()
    plan=RuntimeInstallation.model_validate_json((HERE/'installation.json').read_text())
    review=json.loads((HERE/'operation-review.json').read_text())
    assert digest(plan)==review['installation_sha256']
    assert file_digest(Path(__file__).resolve())==review['driver_sha256']
    assert file_digest(ROOT/'integrations/toolkit/langgraph_fixture.py')==review['worker_sha256']
    for wheel in plan.wheels:
        assert file_digest(Path(plan.wheelhouse)/wheel.filename)==wheel.sha256
    if args.execute_reviewed_digest is None:
        print(json.dumps({'review_sha256':digest(review),'installed':False,'execution':False}));return
    assert args.execute_reviewed_digest==digest(review), 'exact operator review required'
    asyncio.run(check(plan,review))


if __name__=='__main__':
    main()
