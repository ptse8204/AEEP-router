"""Prepared matched executor resource comparator; requires exact frozen review."""
import asyncio,base64,hashlib,json,os,runpy,subprocess,sys,tempfile,time
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'
REVIEW=REPORTS/'native-resource-successor-review.json'
ASSETS=ROOT/'integrations/assessment-runtime'
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
async def child(payload):
    from aeep.assessment.repository import AssessmentRepository
    from aeep.assessment.workbook import workbook_recipe
    from aeep.assessment.workbook_native import implementation_digest,validate
    from aeep.economic.prepared import executor_fingerprint
    from aeep.hosts.codex_sandbox import NativeSandboxConfig,native_backend_digest
    from aeep.hosts.codex_native_process import execute_single_process
    from aeep.mcp.server import AEEPToolService
    from aeep.models import Manifest,SideEffect,TaskScope,ValidationKind,ValidationSpec,utc_now
    from aeep.router import Router
    from aeep.tasks import activate,change_state,inspect
    from aeep.validators import ValidationContext
    root=Path(payload['root']);scratch=root/'scratch';scratch.mkdir();binary=Path(payload['binary'])
    prefix=subprocess.run([str(PYTHON),'-I','-c','import sys;print(sys.prefix)'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
    boundary=NativeSandboxConfig(binary=str(binary),binary_sha256='sha256:'+hashlib.sha256(binary.read_bytes()).hexdigest(),project_root=str(root),read_roots=[str(Path(prefix).resolve())],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON),python_sha256='sha256:'+hashlib.sha256(PYTHON.read_bytes()).hexdigest())
    source=(ASSETS/'workbook_program.py').read_text();program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);print(json.dumps(ns['reference'](json.load(sys.stdin))))";argv=[str(PYTHON),'-I','-c',program]
    grader=runpy.run_path(str(ASSETS/'workbook_grader.py'))['grade']
    helper=runpy.run_path(str(REPORTS/'native-resource-evaluation-288e.py'));inventory=helper['inventory']
    sample={'arm':payload['arm'],'index':payload['index'],'backend_digest':native_backend_digest(boundary),'tasks':[],'retention_checkpoints':[],'config_states':[]}
    router=None;service=None;manifest=root/'aeep.json';host_config=root/'.codex/config.toml'
    def config_state():
        value=host_config.read_bytes() if host_config.exists() else None
        return {'bytes':len(value or b''),'digest':hashlib.sha256(value).hexdigest() if value is not None else None}
    sample['config_states'].append(config_state())
    if payload['arm']=='aeep':
        recipe=workbook_recipe();spec=recipe.extension.reference.model_copy(deep=True);spec.id='native.resource.successor';spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema
        spec.config={**spec.config,'argv':argv,'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(scratch)},'max_output_bytes':200000}
        spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'aeep.workbook.native.v1','implementation_digest':implementation_digest()})]
        manifest.write_text(Manifest(database=str(root/'.aeep/state.db'),executors=[spec]).model_dump_json())
        router=Router.from_manifest(manifest);repo=AssessmentRepository(router.store);repo.review(repo.put('recipe',recipe.recipe_id,recipe))
        scope=TaskScope(scope_id='resource-successor',project_root=str(root),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.READ,max_attempts=len(payload['cases']),max_attempt_seconds=30,expires_at=utc_now()+timedelta(minutes=5))
        scope_digest=repo.put('task_scope',scope.scope_id,scope);repo.review(scope_digest);activation=activate(router,scope.scope_id)
        service=AEEPToolService(router,profile='task',task_activation=activation.activation_id)
        sample.update(scope_digest=scope_digest,activation_id=activation.activation_id,executor_fingerprint=executor_fingerprint(spec),schema_bytes=len(json.dumps(service.list_tools()).encode()),instructions_bytes=len(service.instructions.encode()))
        sample['config_states'].append(config_state());sample['retention_checkpoints'].append({'phase':'activated','disk':inventory(root/'.aeep')})
    try:
        for case in payload['cases']:
            started=time.perf_counter();inp=case['input']
            if service is None:
                result=await execute_single_process(boundary,argv,{'TMPDIR':str(scratch)},json.dumps(inp).encode(),30,200000)
                assert result.exit_code==0 and not result.timed_out and not result.stream_error and not result.cleanup_incomplete and not result.output_truncated
                output=json.loads(result.stdout);required=validate(ValidationContext(inp,output)).valid is True; receipt_id=None;recorded_resources=asdict(result.metrics)
            else:
                tool=service.list_tools()[0]['name'];result=(await service.call(tool,inp))['structuredContent'];assert result['ok'];output=result['output'];receipt=result['receipts'][0];required=receipt['task_valid'] is True and any(c['kind']=='callback' and c['valid'] is True and c['trust']=='verified' for c in receipt['checks']);receipt_id=receipt['receipt_id'];recorded_resources=receipt['recorded_resources']
            independent=grader({'input':inp,'output':output,'expected':case['output']}) is True;assert required and independent
            sample['tasks'].append({'task_wall_ms':(time.perf_counter()-started)*1000,'input_sha256':hashlib.sha256(json.dumps(inp,sort_keys=True).encode()).hexdigest(),'input_json_bytes':len(json.dumps(inp).encode()),'output_json_bytes':len(json.dumps(output).encode()),'output_sha256':hashlib.sha256(json.dumps(output,sort_keys=True).encode()).hexdigest(),'required_validator_valid':required,'independent_grader_valid':independent,'receipt_id':receipt_id,'recorded_resources':recorded_resources})
            if router:sample['retention_checkpoints'].append({'phase':'after_task_'+str(len(sample['tasks'])),'disk':inventory(root/'.aeep')})
        if router:
            change_state(router,activation.activation_id,'uninstall');sample['uninstall_inspection']=inspect(router,activation.activation_id);assert sample['uninstall_inspection']['overlay']=='absent';sample['config_states'].append(config_state())
    finally:
        if router:await router.close()
    if router:
        sample['retention_checkpoints'].append({'phase':'closed','disk':inventory(root/'.aeep')});sample['config_mutations']=sum(a!=b for a,b in zip(sample['config_states'],sample['config_states'][1:]));sample['retained_project_bytes']=sample['retention_checkpoints'][-1]['disk']['logical_bytes']
    print(json.dumps(sample))
async def main():
    from aeep.assessment.verification import verification_source_digest
    from aeep.executors.command import _monitor_process
    import shutil
    review=json.loads(REVIEW.read_text());assert review['execution_authorized'];assert verification_source_digest(ROOT)==review['source_digest'];assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==review['driver_sha256']
    result_path=REPORTS/review['result_filename'];assert not result_path.exists();evidence=ROOT/'.aeep'/review['evidence_directory'];assert not evidence.exists();evidence.mkdir()
    fixtures=subprocess.run([str(PYTHON),'-I',str(ASSETS/'workbook_program.py'),'generate'],input=json.dumps({'seed':review['seed'],'stages':[{'split':'resource_successor','count':3}]}),text=True,capture_output=True,check=True,timeout=15)
    cases=json.loads(fixtures.stdout)['cases'];assert len(cases)==3;samples=[]
    assignments=[(str(i),arm,[case]) for i,case in enumerate(cases) for arm in (('native','aeep') if i%2==0 else ('aeep','native'))]
    if review['retention_growth_specimen']:assignments.append(('retention_growth','aeep',cases))
    for index,arm,selected in assignments:
        with tempfile.TemporaryDirectory(prefix='aeep-resource-successor-') as directory:
            root=Path(directory).resolve();payload={'root':str(root),'binary':review['binary'],'index':index,'arm':arm,'cases':selected};started=time.perf_counter()
            process=await asyncio.create_subprocess_exec(sys.executable,__file__,'--child',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stop=asyncio.Event();monitor=asyncio.create_task(_monitor_process(process.pid,stop))
            try:stdout,stderr=await asyncio.wait_for(process.communicate(json.dumps(payload).encode()),60)
            finally:
                if process.returncode is None:process.kill();await process.wait()
                stop.set();metrics=await monitor
            sample={'index':index,'arm':arm,'process_wall_ms':(time.perf_counter()-started)*1000,'sampled_process_tree':asdict(metrics),'exit_code':process.returncode,'stderr_bytes':len(stderr),'stderr_sha256':hashlib.sha256(stderr).hexdigest()}
            if process.returncode==0:sample.update(json.loads(stdout))
            else:sample['failure']='bounded sample failed; no replay'
            if (root/'.aeep').exists():
                target=evidence/(index+'-'+arm);shutil.copytree(root/'.aeep',target);sample['canonical_store']=str(target)
            samples.append(sample)
            result_path.write_text(json.dumps({'source_digest':review['source_digest'],'review_sha256':hashlib.sha256(REVIEW.read_bytes()).hexdigest(),'samples':samples,'classification':review['classification'],'complete':False,'resource_gate_complete':False},indent=2)+'\n')
            if process.returncode:break
    limits=review['ceilings']
    for sample in samples:
        if sample['arm']!='aeep' or sample['exit_code']!=0:continue
        m=sample['sampled_process_tree'];sample['frozen_bound_checks']={'wall':sample['process_wall_ms']<=limits['process_wall_ms'],'cpu':m['cpu_ms']<=limits['sampled_process_cpu_ms'],'rss':m['peak_memory_mb']<=limits['sampled_process_peak_memory_mb'],'memory_integral':m['memory_mb_seconds']<=limits['sampled_process_memory_mb_seconds'],'retention':sample['retained_project_bytes']<=limits['retained_project_bytes'],'schema':sample['schema_bytes']<=limits['task_schema_bytes'],'config':max(x['bytes'] for x in sample['config_states'])<=limits['project_config_bytes'],'config_mutations':sample['config_mutations']<=limits['project_config_mutations'],'config_restored':sample['config_states'][0]==sample['config_states'][-1]}
    result_path.write_text(json.dumps({'source_digest':review['source_digest'],'review_sha256':hashlib.sha256(REVIEW.read_bytes()).hexdigest(),'samples':samples,'classification':review['classification'],'complete':len(samples)==len(assignments) and all(x['exit_code']==0 for x in samples),'source_unchanged':verification_source_digest(ROOT)==review['source_digest'],'model_turns':0,'raw_payloads_retained':False,'resource_gate_complete':False,'release_ready':False},indent=2)+'\n');print(json.dumps({'result':str(result_path),'samples':len(samples)}))
if __name__=='__main__':asyncio.run(child(json.load(sys.stdin)) if sys.argv[1:]==['--child'] else main())
