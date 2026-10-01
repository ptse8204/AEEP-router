import asyncio,hashlib,json,sys,tempfile
from pathlib import Path
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import ActionRequest,ExecutorKind,SideEffect
async def main():
    binary=Path('/Users/edwintse/.local/bin/codex').resolve()
    with binary.open('rb') as stream: pin='sha256:'+hashlib.file_digest(stream,'sha256').hexdigest()
    rows=[]
    for detached in [False,True]:
        with tempfile.TemporaryDirectory(prefix='aeep-process-probe-') as directory:
            root=Path(directory).resolve(); data=root/'data'; data.mkdir(); marker=data/'marker'
            boundary=NativeSandboxConfig(binary=str(binary),binary_sha256=pin,project_root=str(root),read_roots=[str(Path(sys.prefix).resolve())],write_roots=[str(data)])
            child='import pathlib,sys,time; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text("synthetic effect");'
            parent='import subprocess,sys,time; child=subprocess.Popen([sys.executable,"-I","-c",sys.argv[1],sys.argv[2]],start_new_session='+repr(detached)+',stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(child.pid,flush=True); time.sleep(0.2)'
            spec=reference_spec('csv').model_copy(update={'kind':ExecutorKind.COMMAND,'side_effect':SideEffect.WRITE,'config':{'argv':[sys.executable,'-I','-c',parent,child,str(marker)],'argv_literal':True,'timeout_seconds':2,'output':{'type':'json'},'native_sandbox':boundary.model_dump(mode='json')}})
            raw=await CommandExecutor().execute(ExecutionContext(request=ActionRequest(capability=spec.capability),spec=spec,estimate=spec.estimate,attempt=1))
            await asyncio.sleep(1.0)
            rows.append({'detached':detached,'status':raw.status.value,'observed_background_processes':raw.error_type=='BACKGROUND_PROCESS_REJECTED','effect_after_return':marker.exists(),'elapsed_ms':raw.resources.latency_ms,'child_program_sleep_seconds':0.8,'observation_wait_seconds':1.0,'raw_error_type':raw.error_type})
    report={'source_digest':verification_source_digest(Path.cwd()),'kind':'actual native early-parent-success probe; synthetic temporary effects only','model_calls':0,'coordinator_death_tested':False,'cases':rows}
    Path('reports/v08/steering-v1-delivery-validation/final/process-success-probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
asyncio.run(main())
