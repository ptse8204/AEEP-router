"""Bounded owned-process fault probe; not qualification or benefit evidence."""
import asyncio, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path
from datetime import timedelta
import psutil
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import Manifest, TaskScope, ActionRequest, ActionConstraints, PolicyConfig, SideEffect, utc_now
from aeep.router import Router
ROOT=Path(__file__).resolve().parent
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
WORK=ROOT/'native-coordinator-death-owned-288e'
async def coordinator():
    config=json.loads((WORK/'definition.json').read_text())
    router=Router.from_manifest(WORK/'aeep.json')
    repo=AssessmentRepository(router.store)
    scope=TaskScope.model_validate(config['scope'])
    repo.review(repo.put('task_scope',scope.scope_id,scope))
    router.bind_task_scope(scope.scope_id)
    await router.execute(ActionRequest(capability=config['capability'], policy='write', input={'text':'a\n1','delimiter':','}, constraints=ActionConstraints(max_side_effect=SideEffect.WRITE)), approved_side_effect=SideEffect.WRITE)
    await router.close()
def supervisor():
    WORK.mkdir(exist_ok=False); data=WORK/'data'; data.mkdir()
    pin='sha256:'+hashlib.sha256(BINARY.read_bytes()).hexdigest()
    boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256=pin,project_root=str(WORK),read_roots=[str(Path(sys.prefix).resolve())],write_roots=[str(data)])
    child="import pathlib,sys,time,os; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(2); pathlib.Path(sys.argv[2]).write_text('synthetic effect after coordinator death'); time.sleep(4)"
    program="import subprocess,sys,time; subprocess.Popen([sys.executable,'-I','-c',sys.argv[1],sys.argv[2],sys.argv[3]],start_new_session=True); time.sleep(8)"
    spec=reference_spec('csv').model_copy(update={'kind':'command','side_effect':SideEffect.WRITE,'idempotent':False,'config':{'argv':[sys.executable,'-I','-c',program,child,str(data/'started'),str(data/'effect')],'argv_literal':True,'native_sandbox':boundary.model_dump(mode='json'),'timeout_seconds':10}})
    manifest=Manifest(database=str(WORK/'.aeep'/'state.db'),executors=[spec],policies={'write':PolicyConfig(name='write',constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))})
    (WORK/'aeep.json').write_text(manifest.model_dump_json())
    scope=TaskScope(scope_id='coordinator-death-fixed',project_root=str(WORK),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.WRITE,max_attempts=1,max_attempt_seconds=10,expires_at=utc_now()+timedelta(minutes=5))
    definition={'source_digest':'288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782','binary':str(BINARY),'binary_sha256':pin,'scope':scope.model_dump(mode='json'),'capability':spec.capability,'fault':'SIGKILL only owned coordinator after detached-child started marker; observe 2.5sec then identity-safe cleanup','authority':'AGENTS.md September 27 finite test amendment delegation; parent explicit September 30 instruction','model_calls':0,'cash':0,'runtime_bound_seconds':20,'expected':'no post-coordinator-death effect; durable attempt retained without replay'}
    (WORK/'definition.json').write_text(json.dumps(definition,indent=2))
    review={'definition_sha256':hashlib.sha256((WORK/'definition.json').read_bytes()).hexdigest(),'authority':definition['authority'],'reviewed_before_execution':True}
    (ROOT/'native-coordinator-death-review-288e.json').write_text(json.dumps(review,indent=2))
    started=time.monotonic(); p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'coordinator'],stdout=subprocess.DEVNULL,stderr=open(WORK/'coordinator-stderr.log','w'),env=dict(os.environ,PYTHONPATH=str(ROOT.parents[1]/'src')))
    owner=psutil.Process(p.pid); owned=[owner]; result={}
    try:
        deadline=time.monotonic()+8
        while not (data/'started').exists() and p.poll() is None and time.monotonic()<deadline: time.sleep(.025)
        result['child_started']=(data/'started').exists()
        if not result['child_started']: raise RuntimeError('child did not start; inspect bounded stderr')
        owned.extend(owner.children(recursive=True))
        child_pid=int((data/'started').read_text()); child_handle=psutil.Process(child_pid)
        if not any(x.pid==child_pid and x.create_time()==child_handle.create_time() for x in owned): raise RuntimeError('marker child not verified owned')
        owner.kill(); p.wait(timeout=3)
        time.sleep(2.5)
        result.update(coordinator_exit=p.returncode,effect_after_coordinator_death=(data/'effect').exists(),child_survived=child_handle.is_running())
    finally:
        cleanup=[]
        for handle in reversed(owned):
            try:
                if handle.is_running(): handle.kill(); cleanup.append(handle.pid)
            except psutil.NoSuchProcess: pass
        psutil.wait_procs(owned,timeout=3)
        result['identity_safe_cleanup_signalled_pids']=cleanup
        result['remaining_owned_processes']=[h.pid for h in owned if h.is_running() and h.status()!=psutil.STATUS_ZOMBIE]
        result['elapsed_seconds']=time.monotonic()-started
        result['definition_sha256']=review['definition_sha256']; result['source_digest']=definition['source_digest']; result['binary_sha256']=pin
        result['verdict']='unsupported coordinator-death cleanup' if result.get('effect_after_coordinator_death') else 'bounded probe only; no general containment proof'
        import sqlite3
        db=sqlite3.connect(WORK/'.aeep'/'state.db')
        result['durable_attempts']=db.execute('select state,count(*) from execution_attempts group by state').fetchall(); db.close()
        (ROOT/'native-coordinator-death-result-288e.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result))
if __name__=='__main__': asyncio.run(coordinator()) if sys.argv[1:]==['coordinator'] else supervisor()
