"""Frozen finite resource evaluation; no model turns or inferred host savings."""
import asyncio,hashlib,json,os,runpy,subprocess,sys,tempfile,time
from dataclasses import asdict
from pathlib import Path
import psutil
from aeep.assessment.verification import verification_source_digest
from aeep.executors.command import _monitor_process
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'
REVIEW=REPORTS/'native-resource-evaluation-review-288e.json'
RESULT=REPORTS/'native-resource-evaluation-result-288e.json'
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')

def host():
    memory=psutil.virtual_memory(); io=psutil.disk_io_counters(); cpu=psutil.cpu_times()
    return {'monotonic_seconds':time.perf_counter(),'memory_used_bytes':memory.used,'memory_available_bytes':memory.available,'swap_used_bytes':psutil.swap_memory().used,'cpu_seconds':cpu._asdict(),'disk_io':io._asdict() if io else None,'filesystem_free_bytes':psutil.disk_usage(ROOT).free}

def inventory(directory):
    logical=allocated=count=0; skipped=0
    for parent,dirs,files in os.walk(directory,followlinks=False):
        dirs[:]=[name for name in dirs if not Path(parent,name).is_symlink()]
        for name in files:
            p=Path(parent,name)
            if p.is_symlink(): skipped+=1;continue
            s=p.stat();logical+=s.st_size;allocated+=s.st_blocks*512;count+=1
    return {'files':count,'logical_bytes':logical,'allocated_bytes':allocated,'symlink_files_skipped':skipped}

async def child(payload):
    harness=runpy.run_path(str(REPORTS/'workbook-footprint-calibration-288e.py'))
    await harness['child'](payload)

async def main():
    review=json.loads(REVIEW.read_text()); assert verification_source_digest(ROOT)==review['source_digest'];assert not RESULT.exists()
    began=time.perf_counter(); baseline=[]
    for _ in range(50): baseline.append(host());await asyncio.sleep(.1)
    generated=subprocess.run([str(PYTHON),'-I',str(ROOT/'integrations/assessment-runtime/workbook_program.py'),'generate'],input=json.dumps({'seed':review['fixtures']['seed'],'stages':[{'split':review['fixtures']['split'],'count':3}]}),text=True,capture_output=True,check=True,timeout=15)
    cases=json.loads(generated.stdout)['cases'];assert len(cases)==3
    samples=[]
    for index,case in enumerate(cases):
        for arm in (('native','aeep') if index%2==0 else ('aeep','native')):
            with tempfile.TemporaryDirectory(prefix='aeep-resource-evaluation-') as directory:
                root=Path(directory).resolve(); payload={'arm':arm,'case_name':str(index),'case':{'input':case['input'],'expected':case['output']},'root':str(root)}
                observations=[host()]; started=time.perf_counter()
                process=await asyncio.create_subprocess_exec(sys.executable,__file__,'--child',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                stop=asyncio.Event();monitor=asyncio.create_task(_monitor_process(process.pid,stop))
                communicate=asyncio.create_task(process.communicate(json.dumps(payload).encode()))
                try:
                    while not communicate.done():
                        observations.append(host());await asyncio.sleep(.05)
                        if time.perf_counter()-started>60:raise TimeoutError('bounded resource sample')
                    stdout,stderr=await communicate
                finally:
                    if process.returncode is None:process.kill();await process.wait()
                    stop.set();metrics=await monitor
                observations.append(host())
                if process.returncode:raise RuntimeError(stderr.decode()[:1000])
                sample=json.loads(stdout);sample.update(index=index,process_wall_ms=(time.perf_counter()-started)*1000,sampled_process_tree=asdict(metrics),whole_host_samples=observations)
                if arm=='aeep':
                    sample['retained_files_after_close']=inventory(root/'.aeep');sample['project_config_bytes']=(root/'.codex/config.toml').stat().st_size if (root/'.codex/config.toml').exists() else 0
                samples.append(sample)
    await asyncio.sleep(.2)
    lab=await asyncio.to_thread(inventory,ROOT/'.aeep')
    limits=review['ceilings'];checks=[]
    for sample in samples:
        if sample['arm']!='aeep':continue
        metrics=sample['sampled_process_tree']; tests={'process_wall':sample['process_wall_ms']<=limits['process_wall_ms'],'process_cpu':metrics['cpu_ms']<=limits['sampled_process_cpu_ms'],'process_rss':metrics['peak_memory_mb']<=limits['sampled_process_peak_memory_mb'],'process_memory_integral':metrics['memory_mb_seconds']<=limits['sampled_process_memory_mb_seconds'],'retention':sample['retained_files_after_close']['logical_bytes']<=limits['retained_project_bytes'],'schema':sample['schema_bytes']<=limits['task_schema_bytes'],'uninstalled_config_absent':sample['project_config_bytes']==0,'required_validator':sample['required_validator_valid'] is True,'independent_grader':sample['recipe_grader_valid'] is True}
        checks.append({'index':sample['index'],'checks':tests,'local_dimensions_within_frozen_bounds':all(tests.values())})
    report={'source_digest':review['source_digest'],'review_sha256':hashlib.sha256(REVIEW.read_bytes()).hexdigest(),'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'baseline_whole_host':baseline,'samples':samples,'local_checks':checks,'assessment_lab_disk_inventory':lab,'measurement_wall_seconds':time.perf_counter()-began,'model_turns':0,'source_unchanged':verification_source_digest(ROOT)==review['source_digest'],'resource_gate_complete':False,'release_ready':False,'limitations':review['unknowns']+['Process sampling lower bound; RSS shared pages may double count.','Whole-host samples include unrelated concurrent work; no causal incremental pass.','Three bounded workbook resources samples cannot establish general workload acceptance.']}
    RESULT.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(RESULT),'samples':len(samples),'local_checks':checks,'assessment_lab_disk_inventory':lab}))
if __name__=='__main__':asyncio.run(child(json.load(sys.stdin)) if sys.argv[1:]==['--child'] else main())
