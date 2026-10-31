"""Exact retained runtime + real optional SDK check. Preparation is inert."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Load only the recorded first-party coordinator snapshot, never changing checkout code.
FROZEN_SOURCE = Path('/Users/edwintse/Documents/aeep-toolkit-v2/.aeep/stack-frozen-source-f1fe5413')
sys.path.insert(0, str(FROZEN_SOURCE/'src'))

from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import RuntimeInstallation, apply, digest, file_digest, snapshot

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


def verify():
    review=json.loads((HERE/'operation-review.json').read_text())
    assert file_digest(Path(__file__))==review['driver_sha256']
    assert file_digest(HERE/'functional-check.py')==review['worker_sha256']
    assert verification_source_digest(FROZEN_SOURCE)==review['checkout_source']
    assert file_digest(HERE/'source-snapshot.json')==review['source_snapshot_manifest_sha256']
    manifest=json.loads((HERE/'source-snapshot.json').read_text())
    assert str(FROZEN_SOURCE)==manifest['snapshot_path'] and manifest['source_digest']==review['checkout_source']
    for name,expected in manifest['files'].items():
        assert file_digest(FROZEN_SOURCE/name)==expected
    plan=RuntimeInstallation.model_validate_json((HERE/'installation.json').read_text())
    assert digest(plan)==review['installation_digest']
    for wheel in plan.wheels:
        assert file_digest(Path(plan.wheelhouse)/wheel.filename)==wheel.sha256
    return review,plan


async def run(review,plan,approval_sha):
    execution=HERE/'execution';execution.mkdir(mode=0o700)
    facts={'review_sha256':approval_sha,'model_calls':0,'candidate_value':'NOT_ASSESSED',
           'selection_value':'NOT_ASSESSED','components':{}}
    (HERE/'execution-started.json').write_text(json.dumps({'review_sha256':approval_sha})+'\n')
    runtime=Path(plan.destination)
    store=ReceiptStore(execution/'outer-receipts.sqlite3')
    began=time.monotonic()
    try:
        previous=HERE.parent/'langgraph-runtime/execution/installation.json'
        assert file_digest(previous)==review['prior_installation_state_sha256']
        installed=json.loads(previous.read_text())
        assert installed['status']=='installed' and installed['plan_sha256']==digest(plan)
        assert snapshot(runtime)==installed['applied_tree_sha256']
        (execution/'installation.json').write_text(json.dumps(installed,indent=2)+'\n')
        original=snapshot(runtime)
        facts['components']['retained-runtime-identity']={'passed':True,'installation_repeated':False,'runtime_retained':True}
        working=execution/'owned-work';working.mkdir(mode=0o700)
        for name in ('home','tmp'): (working/name).mkdir(mode=0o700)
        worker=working/'functional-check.py';worker.write_bytes((HERE/'functional-check.py').read_bytes())
        assert file_digest(worker)==review['worker_sha256']
        profile=working/'boundary.sb'
        profile.write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
            +'(allow file-write* (literal "/dev/null"))\n'
            +'(allow file-write* (subpath '+json.dumps(str(working))+'))\n'
            +'(deny file-read* (subpath '+json.dumps(str(Path.home().resolve()))+'))\n'
            +'(allow file-read* (subpath '+json.dumps(str(runtime))+'))\n'
            +'(allow file-read* (subpath '+json.dumps(str(working))+'))\n'
            +'(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in runtime.parents if p.is_relative_to(Path.home()))+')\n')
        assert file_digest(profile)==review['profile_sha256']
        prefix=['/usr/bin/sandbox-exec','-f',str(profile),str(runtime/'bin/python'),'-B']
        env={'PATH':'/usr/bin:/bin','HOME':str(working/'home'),'TMPDIR':str(working/'tmp'),
             'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}
        # Only owned canaries are used: no credential path is inspected.
        outside=execution/'outside-write-canary';assert not outside.exists()
        canary=HERE/'functional-check.py'
        code='import json,pathlib,socket,sys;d={}\ntry:pathlib.Path(sys.argv[1]).read_bytes()\nexcept PermissionError:d["home_read_denied"]=True\ntry:pathlib.Path(sys.argv[2]).write_text("owned-probe")\nexcept PermissionError:d["outside_write_denied"]=True\nwith socket.socket() as s:\n try:s.connect(("127.0.0.1",9))\n except PermissionError:d["network_denied"]=True\nprint(json.dumps(d))'
        result=subprocess.run([*prefix,'-c',code,str(canary),str(outside)],cwd=working,env=env,
                              capture_output=True,timeout=20,check=False)
        (execution/'preflight-process.json').write_text(json.dumps({'returncode':result.returncode,'stdout':result.stdout[:8192].decode(errors='replace'),'stderr':result.stderr[:8192].decode(errors='replace')},indent=2)+'\n')
        assert result.returncode==0,'preflight failed; bounded diagnostics retained'
        checks=json.loads(result.stdout)
        if outside.exists():
            assert outside.read_text()=='owned-probe';outside.unlink()
        assert result.returncode==0 and checks==dict(home_read_denied=True,outside_write_denied=True,network_denied=True)
        (execution/'sandbox-preflight.json').write_text(json.dumps(checks,indent=2)+'\n')
        # Installation and SDK/presentation are independent component attempts.
        async def execute(name, argv, payload=None, seconds=90):
            spec=ExecutorSpec(id='toolkit.'+name,capability='toolkit.upstream-engineering@1',kind='command',
                description='Exact reviewed offline component check; no model/provider',side_effect='write',
                config={'argv':argv,'argv_literal':True,'inherit_env':False,'env':env,'cwd':str(working),
                        'stdin_json':payload is not None,'timeout_seconds':seconds,'max_output_bytes':1048576,
                        'output':{'type':'json'}})
            action=ActionRequest(capability=spec.capability,input=payload or {})
            context=ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,approved_side_effect=SideEffect.WRITE)
            executor=CommandExecutor();started=utc_now()
            try:raw=await (await executor.start(context)).task
            finally:await executor.close()
            receipt=ExecutionReceipt(decision_id='reviewed-'+name,action_id=action.action_id,
                capability=spec.capability,executor_id=spec.id,executor_kind=spec.kind,status=raw.status,
                started_at=started,ended_at=utc_now(),estimated=spec.estimate,actual_resources=raw.resources,
                accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,
                metadata={'review_sha256':approval_sha,'evidence_kind':'upstream_engineering',**raw.metadata})
            store.save_receipt(receipt)
            if isinstance(raw.output,dict):
                (execution/(name+'.json')).write_text(json.dumps(raw.output,indent=2)+'\n')
            facts['components'][name]={'passed':receipt.execution_success,'receipt_id':receipt.receipt_id,'status':raw.status.value,'error_type':raw.error_type,'error_message':str(raw.error_message)[:8192] if raw.error_message else None}
            return raw
        raw=await execute('langgraph-sdk', [*prefix,str(worker)],
            {'review_sha256':approval_sha,'canary_path':str(canary),'installed_source':review['installed_source']})
        if raw.status.value=='success':
            assert len(raw.output['checks'])==4 and all(c['passed'] for c in raw.output['checks'])
            assert raw.output['operations']==6 and raw.output['models']==0
        package_code='import importlib.metadata,json;from aeep_toolkit.stack_readiness import checklist;from aeep_toolkit.benchmarks import initial_catalog;from aeep.assessment.verification import verification_source_digest;from pathlib import Path;import aeep.assessment.verification as v;print(json.dumps({"version":importlib.metadata.version("aeep-agent-router"),"requirements":len(checklist()["components"]),"tasks":len(initial_catalog()["tasks"]),"installed_source":verification_source_digest(Path(v.__file__).resolve().parents[3])}))'
        package=await execute('installed-package', [*prefix,'-c',package_code],seconds=30)
        if package.status.value=='success':
            assert package.output['version']=='0.8.2' and package.output['requirements']==19 and package.output['tasks']==6
            assert package.output['installed_source']==review['installed_source']
        facts['runtime_unchanged']=snapshot(runtime)==original
        facts['runtime_retained']=True
    except BaseException as error:
        facts['error_type']=type(error).__name__
        facts['passed']=False
    finally:
        store.close()
        facts['wall_seconds']=time.monotonic()-began
        facts['passed']=not facts.get('error_type') and bool(facts['components']) and all(c['passed'] for c in facts['components'].values())
        facts['all_stack_integrations_complete']=False
        (execution/'summary.json').write_text(json.dumps(facts,indent=2)+'\n')
        print(json.dumps(facts))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
    review,plan=verify();sha=file_digest(HERE/'operation-review.json')
    if args.execute_approved is None:
        print(json.dumps({'review_sha256':sha,'wheel_count':len(plan.wheels),'installed':False,'executed':False}));return
    assert args.execute_approved==sha
    gates=json.loads((HERE.parent/'verification/checks.json').read_text())
    assert gates['source_before']==gates['source_after']==review['checkout_source']
    assert len(gates['checks'])==13 and all(check['exit_code']==0 for check in gates['checks'])
    approval=json.loads((HERE/'operator-approval.json').read_text())
    assert approval['approved'] is True and approval['review_sha256']==sha
    assert not (HERE/'execution-started.json').exists() and not (HERE/'execution').exists()
    assert shutil.disk_usage(ROOT).free>50*1024**3+review['disk_reservation_bytes']
    asyncio.run(run(review,plan,sha))


if __name__=='__main__':main()
