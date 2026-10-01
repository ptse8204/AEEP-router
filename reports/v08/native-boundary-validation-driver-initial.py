"""Exact-argv validation for a frozen execution-boundary change; no live models."""
import hashlib,json,os,shlex,subprocess,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/v08'
REVIEW=REPORTS/'native-boundary-validation-review.json'
def main():
    review=json.loads(REVIEW.read_text());assert review['execution_authorized'];source=review['source_digest'];assert verification_source_digest(ROOT)==source
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==review['driver_sha256'];tag=source[:12]
    result=REPORTS/('delivery-boundary-validation-'+tag+'.json');assert not result.exists()
    scratch=Path(tempfile.mkdtemp(prefix='aeep-boundary-validation-')).resolve();coverage=scratch/'coverage.data';coverage_json=REPORTS/('delivery-boundary-coverage-'+tag+'.json')
    common={'PYTHONPATH':str(ROOT/'src'),'AEEP_NATIVE_CODEX':review['binary'],'AEEP_NATIVE_WORKBOOK_PYTHON':review['workbook_python']}
    container={**common,'AEEP_CONTAINER_IMAGE':'sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228','AEEP_WORKBOOK_IMAGE':'sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228','AEEP_CATALOG_METRICS_IMAGE':'sha256:4fa7164eab77de79c57ef4ff538d466be334f1cb582f8ebab7740489f5cd5ce7','AEEP_INSPECTION_FIXTURE_SPECS':str(REPORTS/'offline-inspection-fixture-specs.json'),'AEEP_CONTAINER_RUNTIME':'/usr/local/bin/docker','AEEP_CONTAINER_SOCKET':'/Users/edwintse/.docker/run/docker.sock'}
    checks=[]
    def run(name,argv,overrides=None,cwd=ROOT,timeout=1200):
        assert verification_source_digest(ROOT)==source
        started=time.perf_counter();log=REPORTS/('delivery-boundary-'+name+'-'+tag+'.log');assert not log.exists();env=dict(os.environ);env.update(common);env.update(overrides or {})
        record={'name':name,'argv':argv,'cwd':str(cwd),'environment_overrides':common| (overrides or {}),'log':log.name,'recorded_at':datetime.now(timezone.utc).isoformat(),'command_spelling_exact':True,'timeout_seconds':timeout}
        with log.open('xb') as stream:
            stream.write(('Exact argv: '+shlex.join(argv)+'\n').encode());stream.flush()
            try:completed=subprocess.run(argv,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout);record['exit_code']=completed.returncode
            except subprocess.TimeoutExpired:record['exit_code']=None;record['timed_out']=True
        record['wall_seconds']=time.perf_counter()-started;record['source_unchanged']=verification_source_digest(ROOT)==source;checks.append(record)
        result.write_text(json.dumps({'source_digest':source,'review_sha256':hashlib.sha256(REVIEW.read_bytes()).hexdigest(),'scratch_directory':str(scratch),'checks':checks,'complete':False,'release_ready':False},indent=2)+'\n')
        print(json.dumps({'name':name,'exit_code':record['exit_code'],'wall_seconds':record['wall_seconds'],'source_unchanged':record['source_unchanged']}),flush=True)
        if record['exit_code']!=0 or not record['source_unchanged']:raise RuntimeError('validation stopped: '+name)
    py=sys.executable
    run('compileall',[py,'-m','compileall','-q','src','examples','tests'])
    run('schema',[py,'scripts/generate_schemas.py','--check'])
    run('ruff',['ruff','check','.'])
    run('mypy',['mypy','src'])
    run('policy',[py,'scripts/check_assessment_policy.py'])
    run('pytest',[py,'-m','pytest','-q','--basetemp='+str(scratch/'pytest')])
    run('coverage-pytest',[py,'-m','coverage','run','--branch','-m','pytest','-q','--basetemp='+str(scratch/'coverage')],{'COVERAGE_FILE':str(coverage)})
    run('coverage-report',[py,'-m','coverage','report','-m'],{'COVERAGE_FILE':str(coverage)})
    run('coverage-json',[py,'-m','coverage','json','-o',str(coverage_json)],{'COVERAGE_FILE':str(coverage)})
    run('critical-coverage',[py,'scripts/check_critical_coverage.py',str(coverage_json)])
    run('assessment-coverage',[py,'scripts/check_assessment_coverage.py',str(coverage_json)])
    run('container-all',[py,'-m','pytest','-q','-rs','-m','real_container','--basetemp='+str(scratch/'container')],container)
    run('node',['npm','test'],cwd=ROOT/'integrations/dsh-aeep-router')
    run('economic',[py,'examples/economic_evidence/campaign.py','--repetitions','30','--check','--require-gates'])
    run('dsh',[py,'examples/dsh_campaign/campaign.py','--check'])
    run('dsh-live',[py,'examples/dsh_campaign/live_campaign.py','--check-report','reports/v05/dsh/live-safety.json'])
    run('dsh-comparison',[py,'examples/dsh_campaign/live_campaign.py','--check-comparison','reports/v05/dsh/live-comparison.json'])
    run('dsh-native-plan',[py,'examples/dsh_campaign/live_campaign.py','--check-native-plan'])
    run('job',[py,'examples/job_application/campaign.py','--check'])
    run('provider',[py,'-m','aeep','provider','verify','examples/provider_package/aeep-provider.yaml','-m','examples/provider_package/aeep.yaml','--compact'])
    run('router-complete',[py,'-m','aeep','verify','router-complete','--profile','all','--strict','--json'])
    run('package-build',[py,'-m','build','--no-isolation'])
    value=json.loads(result.read_text());value.update(complete=True,source_unchanged=verification_source_digest(ROOT)==source,coverage=json.loads(coverage_json.read_text())['totals']);result.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({'result':str(result),'complete':True}),flush=True)
if __name__=='__main__':main()
