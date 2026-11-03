"""Approved finite source verification with actual host-capacity monitoring."""
from __future__ import annotations
import argparse,json,os,shutil,signal,subprocess,sys,time
from datetime import UTC,datetime
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import file_digest

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--approved-review',required=True);args=parser.parse_args()
    review=json.loads((HERE/'operation-review.json').read_bytes())
    assert args.approved_review==file_digest(HERE/'operation-review.json')
    approval=json.loads((HERE/'operator-approval.json').read_bytes())
    assert approval['approved'] is True and approval['review_sha256']==args.approved_review
    for name,expected in review['bound_files'].items():assert file_digest(ROOT/name)==expected,name
    exception=json.loads((HERE/'storage-exception.json').read_bytes())
    out=HERE/'verification';out.mkdir(mode=0o700)
    completed=json.loads(Path(review['completed_source_checks']).read_bytes())
    assert completed['source_before']==completed['source_after']==review['source']
    assert len(completed['checks'])==7 and completed['checks'][6]['name']=='coverage-tests' and completed['checks'][6]['exit_code']==125
    assert all(x['exit_code']==0 for x in completed['checks'][:6])
    prepared=json.loads((HERE/'preparation/checks.json').read_bytes())
    initial={c['name']:c for c in prepared['checks']}
    source=verification_source_digest(ROOT);assert source==review['source']
    record={'source_before':source,'source_after':source,'checks':completed['checks'][:6],
        'reused_exact_source_preparation':['compileall','schemas','assessment-policy','ruff','mypy','pytest','build'],
        'scope':'Coverage-only completion. Reuse the six exact-source successful gates including full pytest, plus the completed build. Shared-host net changes are diagnostic only; actual free space must remain at least50GiB. Synthetic capacity in installer unit fixtures is not a host measurement.',
        'models':0,'comparisons':'PAUSED','capacity_samples':[]}
    checks=[('coverage-tests',['-m','coverage','run','--branch','-m','pytest']),
        ('coverage-json',['-m','coverage','json','-o',str(out/'coverage.json')]),
        ('coverage-report',['-m','coverage','report','-m']),
        ('critical-coverage',['scripts/check_critical_coverage.py',str(out/'coverage.json')]),
        ('assessment-coverage',['scripts/check_assessment_coverage.py',str(out/'coverage.json')]),
        ('toolkit-integration-fixtures',['-m','pytest','integrations/toolkit'])]
    assert not os.environ.get('PYTEST_ADDOPTS'),'Unexpected inherited test options'
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src')+':'+str(HERE.parent/'workflow-scanner-20261102'),PYTHONDONTWRITEBYTECODE='1')
    env['PYTEST_ADDOPTS']='-o tmp_path_retention_policy=all -o tmp_path_retention_count=10000'
    assert not any(key.startswith(('AEEP_REAL_','AEEP_LIVE_')) and value for key,value in env.items()),'Live selectors must be absent'
    started=time.monotonic()

    def capacity():
        free=shutil.disk_usage(ROOT).free;now=datetime.now(UTC)
        baseline=json.loads((HERE/'host-capacity-start.json').read_bytes())['available_free_bytes']
        observation={'observed_at':now.isoformat(),'available_free_bytes':free,'net_host_drop_bytes':baseline-free,'host_delta_is_not_task_attribution':True}
        record['capacity_samples'].append(observation)
        assert datetime.fromisoformat(exception['issued_at'].replace('Z','+00:00'))<=now<datetime.fromisoformat(exception['expires_at'].replace('Z','+00:00'))
        assert ROOT.stat().st_dev==exception['filesystem_device']
        assert free>=review['hard_minimum_free_bytes'],'Original 50GiB host reserve crossed'
        # Shared-host net changes are recorded, never used as task-allocation estimates.
        assert time.monotonic()-started<3600,'Finite verification time exhausted'
        assert verification_source_digest(ROOT)==source,'Source drifted during verification'

    for name,args in checks:
        capacity()
        if name in {'pytest','coverage-tests'}:
            # Only this run's passing fixtures are removed after teardown. Preserve older roots.
            args=[*args,'-p','aeep_fixture_cleanup','-o','tmp_path_retention_policy=all','-o','tmp_path_retention_count=10000']
            env['AEEP_FIXTURE_CLEANUP_RECORD']=str(out/(name+'-fixture-cleanup.json'))
        else:env.pop('AEEP_FIXTURE_CLEANUP_RECORD',None)
        clock=time.monotonic();stop=None;reason=None
        with (out/(name+'.log')).open('x') as log:
            process=subprocess.Popen([sys.executable,*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                while process.poll() is None:
                    time.sleep(1);capacity()
                    assert log.tell()<16*1024**2,'Bounded verification log exceeded'
            except BaseException as error:
                stop=type(error).__name__;reason=str(error)[:512]
                for sig,seconds in ((signal.SIGINT,10),(signal.SIGTERM,5),(signal.SIGKILL,5)):
                    if process.poll() is not None:break
                    try:os.killpg(process.pid,sig)
                    except ProcessLookupError:break
                    try:process.wait(timeout=seconds)
                    except subprocess.TimeoutExpired:continue
                process.wait(timeout=5)
        item={'name':name,'argv':[sys.executable,*args],'exit_code':process.returncode if stop is None else 125,
              'process_exit_code':process.returncode,'elapsed_seconds':time.monotonic()-clock,'monitor_stop':stop,'monitor_reason':reason}
        record['checks'].append(item);record['source_after']=verification_source_digest(ROOT)
        (out/'checks.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(item),flush=True)
        if item['exit_code'] or record['source_after']!=source:return 1
    record['checks'].append(initial['build']);capacity()
    record['source_after']=verification_source_digest(ROOT)
    (out/'checks.json').write_text(json.dumps(record,indent=2)+'\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
