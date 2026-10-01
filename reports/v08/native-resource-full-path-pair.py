"""One exploratory zero-model fresh-process native/AEEP pair; no gate claim."""
import asyncio,ast,hashlib,json,os,subprocess,sys,tempfile,time,shutil
import psutil
from pathlib import Path
from dataclasses import asdict
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.executors.command import _monitor_process
from aeep.models import StrictModel
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/v08';ASSETS=ROOT/'integrations/assessment-runtime'
SOURCE='f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
class Definition(StrictModel):
    source_digest:str
    files_sha256:dict[str,str]
    binary_sha256:str
    python_sha256:str
    guard_sha256:str
    fixture_seed:int=107
    fixture_count:int=3
    fixture_index:int=1
    maximum_operations:int=1
    maximum_model_turns:int=0
    maximum_seconds:int=160
    arms:list[str]=['stdlib_native','generated_project_mcp_aeep']
    frozen_checks:dict[str,float]={'process_wall_ms':5000,'sampled_process_cpu_ms':4000,'sampled_process_peak_memory_mb':768,'sampled_process_memory_mb_seconds':1500,'retained_project_bytes':8388608,'task_schema_bytes':16384,'project_config_bytes':1024}
    classification:str='n1 software-only incremental fresh-process footprint; no model workflow, qualification, marginal capability benefit or release/resource gate'
async def monitored(argv,stdin,timeout):
    started=time.perf_counter();p=await asyncio.create_subprocess_exec(*argv,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=str(ROOT))
    stop=asyncio.Event();monitor=asyncio.create_task(_monitor_process(p.pid,stop));owned={}
    async def identities():
        while not stop.is_set():
            try:
                parent=psutil.Process(p.pid)
                for child in [parent,*parent.children(recursive=True)]:
                    try:owned[(child.pid,child.create_time())]=child
                    except psutil.Error:pass
            except psutil.Error:pass
            await asyncio.sleep(.01)
    identity_task=asyncio.create_task(identities())
    try:out,err=await asyncio.wait_for(p.communicate(stdin),timeout)
    finally:
        if p.returncode is None:p.kill();await p.wait()
        stop.set();metrics=await monitor;await identity_task
        survivors=[]
        for (pid,created),child in owned.items():
            try:
                if child.is_running() and child.status()!=psutil.STATUS_ZOMBIE:
                    survivors.append({'pid':pid,'create_time':created});child.kill();await asyncio.to_thread(child.wait,timeout=1)
            except psutil.NoSuchProcess:pass
        assert not survivors,'owned descendant survived native EOF; cleaned by creation-time handle'
    assert p.returncode==0,'bounded stage failed; no retry'
    return json.loads(out),{'wall_ms':(time.perf_counter()-started)*1000,'sampled_process_tree':asdict(metrics),'stderr_bytes':len(err),'exit_code':p.returncode,'owned_process_identities_observed':len(owned),'owned_survivors':survivors}
async def main():
    assert verification_source_digest(ROOT)==SOURCE
    resultpath=REPORTS/'native-resource-full-path-pair-result.json';assert not resultpath.exists()
    native=REPORTS/'native-no-aeep-baseline-child.py';aeep=REPORTS/'native-sol61-resource-full-path-aeep.py'
    guardnode=next(x.value for x in ast.parse((ROOT/'src/aeep/hosts/codex_native_process.py').read_text()).body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SINGLE_PROCESS_GUARD' for t in x.targets));guard=ast.literal_eval(guardnode)
    paths=[Path(__file__),native,aeep,ROOT/'src/aeep/hosts/codex_native_process.py',ASSETS/'workbook_program.py',ASSETS/'workbook_grader.py',ROOT/'src/aeep/assessment/workbook_native.py']
    definition=Definition(source_digest=SOURCE,files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),python_sha256=hashlib.sha256(PYTHON.read_bytes()).hexdigest(),guard_sha256=hashlib.sha256(guard.encode()).hexdigest())
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(router.store);old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    mapping=repo.put('native_resource_pair','full-path-pair',definition);repo.review(mapping);req=old.model_copy(update={'plan_id':'planning_native_resource_full_path_pair','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]});digest=repo.put('planning_request',req.plan_id,req);repo.review(digest);repo.authorize(req)
    review={'authority':'standing September25/27 finite exact review; parent authorized one software-only pair','definition':definition.model_dump(),'mapping_digest':mapping,'request_digest':digest,'authentication':'Codex-owned, no auth state accessed','measurement':'each fresh coordinator and owned descendants, startup through cleanup; external verifier stage included in end-to-end totals; setup reported separately; sampled peaks never added across sequential stages','limits':'existing frozen local checks unchanged, n1 exploratory; no retrospective engineering threshold changes','nested_aeep_accounting':'AEEP arm separately reserves its existing supported fixture/host operations; wrapper reservation covers baseline, generation, verifier and measurement overhead only'}
    (REPORTS/'native-resource-full-path-pair-review.json').write_text(json.dumps(review,indent=2)+'\n');operation='native-resource-pair:'+req.plan_id;repo.reserve(req,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=160),stage='native_resource_full_path_pair')
    started=time.perf_counter();separately_debited_aeep_seconds=0.0
    record={'source_digest':SOURCE,'classification':definition.classification,'model_turns':0,'review_sha256':hashlib.sha256((REPORTS/'native-resource-full-path-pair-review.json').read_bytes()).hexdigest(),'resource_gate_complete':False,'samples':[]};directory=None
    try:
        cases,setup=await monitored([str(PYTHON),'-I',str(ASSETS/'workbook_program.py'),'generate'],json.dumps({'seed':107,'stages':[{'split':'demo','count':3}]}).encode(),15);case=cases['cases'][1];record['fixture_generation_stage']=setup
        directory=Path(tempfile.mkdtemp(prefix='aeep-native-resource-baseline-',dir=ROOT));scratch=directory/'scratch';scratch.mkdir()
        prefix=subprocess.run([str(PYTHON),'-I','-c','import sys;print(sys.prefix)'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
        boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+definition.binary_sha256,project_root=str(directory),read_roots=[str(Path(prefix).resolve()),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON),python_sha256='sha256:'+definition.python_sha256)
        source=(ASSETS/'workbook_program.py').read_text();program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);inp=json.load(sys.stdin);print(json.dumps(ns['reference'](inp)))"
        payload={'binary':str(BINARY),'binary_sha256':definition.binary_sha256,'python':str(PYTHON),'python_sha256':definition.python_sha256,'guard':guard,'guard_sha256':definition.guard_sha256,'permission_overrides':['-c','features.apps=false',*boundary.permission_overrides()],'root':str(directory),'argv':[str(PYTHON),'-I','-c',program],'environment':{'TMPDIR':str(scratch)},'input':case['input']}
        baseline,metrics=await monitored([sys.executable,'-I',str(native)],json.dumps(payload).encode(),50);output=baseline.pop('output');assert not baseline['aeep_modules_present'] and baseline['cleanup_confirmed'] and not baseline.get('target_cleanup_intervention')
        verifier="import json,sys,runpy;from aeep.assessment.workbook_native import validate;from aeep.validators import ValidationContext;p=json.load(sys.stdin);required=validate(ValidationContext(p['input'],p['output'])).valid is True;independent=runpy.run_path(p['grader'])['grade'](p) is True;print(json.dumps({'required_validator_valid':required,'independent_grader_valid':independent}));assert required and independent"
        checks,verify_metrics=await monitored([sys.executable,'-c',verifier],json.dumps({'input':case['input'],'output':output,'expected':case['output'],'grader':str(ASSETS/'workbook_grader.py')}).encode(),15)
        record['samples'].append({'arm':'stdlib_native','execution':metrics,'external_verifier':verify_metrics,'checks':checks,'native_metadata':baseline,'output_sha256':hashlib.sha256(json.dumps(output,sort_keys=True).encode()).hexdigest(),'retained_project_bytes':sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()),'schema_bytes':0,'project_config_bytes':0,'model_context_tokens':0})
        aeepout,aeepmetrics=await monitored([sys.executable,str(aeep)],b'',100);aeepresult=json.loads((REPORTS/'native-sol61-resource-full-path-aeep-result-288e.json').read_text());separately_debited_aeep_seconds=aeepresult['setup_elapsed_seconds']+aeepresult['elapsed_seconds'];assert aeepresult['journey_passed'] and aeepresult['host_cleanup_confirmed']
        record['samples'].append({'arm':'generated_project_mcp_aeep','execution_including_setup_and_verifier':aeepmetrics,'detail_result':'native-sol61-resource-full-path-aeep-result-288e.json','schema_bytes':aeepresult['schema_bytes'],'project_config_bytes':aeepresult['project_config_bytes'],'retained_project_bytes':sum(p.stat().st_size for p in (ROOT/'.aeep/native-sol61-resource-full-path-aeep-evidence').rglob('*') if p.is_file()),'instructions_bytes':aeepresult['instructions_bytes'],'model_context_tokens':0,'checks':aeepresult['checks']})
        for sample in record['samples']:
            stages=[sample[key] for key in ('execution','external_verifier','execution_including_setup_and_verifier') if key in sample]
            sample['total_end_to_end_wall_ms']=sum(x['wall_ms'] for x in stages)
            sample['total_sampled_cpu_ms']=sum(x['sampled_process_tree']['cpu_ms'] for x in stages)
            sample['observed_peak_memory_mb']=max(x['sampled_process_tree']['peak_memory_mb'] for x in stages)
            sample['total_sampled_memory_mb_seconds']=sum(x['sampled_process_tree']['memory_mb_seconds'] for x in stages)
            limits=definition.frozen_checks
            sample['frozen_bound_checks']={'wall':sample['total_end_to_end_wall_ms']<=limits['process_wall_ms'],'cpu':sample['total_sampled_cpu_ms']<=limits['sampled_process_cpu_ms'],'rss':sample['observed_peak_memory_mb']<=limits['sampled_process_peak_memory_mb'],'memory_integral':sample['total_sampled_memory_mb_seconds']<=limits['sampled_process_memory_mb_seconds'],'retention':sample['retained_project_bytes']<=limits['retained_project_bytes'],'schema':sample['schema_bytes']<=limits['task_schema_bytes'],'project_config':sample['project_config_bytes']<=limits['project_config_bytes']}
        record['complete']=True
    except BaseException as error:record.update(complete=False,error_type=type(error).__name__,replay_allowed=False)
    finally:
        if directory:shutil.rmtree(directory)
        elapsed=time.perf_counter()-started;repo.finish_operation(operation,elapsed_seconds=max(0,elapsed-separately_debited_aeep_seconds));await router.close();record.update(total_pair_wall_seconds=elapsed,separately_debited_aeep_seconds=separately_debited_aeep_seconds,wrapper_debited_elapsed_seconds=max(0,elapsed-separately_debited_aeep_seconds),source_unchanged=verification_source_digest(ROOT)==SOURCE,telemetry_unknown=['network packet/byte counts','host-level subscription context usage (no model turns)','unobserved between-sample CPU/RSS lifetimes'],raw_payloads_retained=False);resultpath.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'complete':record.get('complete'),'result':str(resultpath),'elapsed_seconds':elapsed}))
asyncio.run(main())
