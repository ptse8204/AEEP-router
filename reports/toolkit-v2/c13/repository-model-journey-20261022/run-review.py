"""Execute the exact gated development bundle once, preserving all failure evidence."""
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from aeep.assessment.verification import verification_source_digest
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,data):
    with path.open('x') as stream:json.dump(data,stream,indent=2);stream.write('\n')


async def main():
    assert len(sys.argv)==2 and sha(HERE/'operation-review.json')==sys.argv[1]
    review=json.loads((HERE/'operation-review.json').read_text());approval=json.loads((HERE/'operator-approval.json').read_text());assert approval['approved'] and approval['review_sha256']==sys.argv[1]
    assert verification_source_digest(ROOT)==review['source_digest']
    for name,digest in review['assets'].items():assert sha(Path(name))==digest
    assert not (HERE/'execution-started.json').exists()
    router=Router.from_manifest(BASE/'aeep.json')
    try:
        before=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        from aeep.assessment.service import AssessmentService
        grant=AssessmentService(router,BASE/'.aeep/assessments').repository.current_grant('onboarding')
        assert before[0]+review['maximum_operations']<=grant.limits.max_operations
        assert before[1]+review['maximum_model_turns']<=grant.limits.max_model_turns
        assert before[2]+review['maximum_reserved_seconds']<=grant.limits.max_elapsed_seconds
    finally:await router.close()
    save(HERE/'execution-started.json',{'review_sha256':sys.argv[1],'grant_before':before,'automatic_retry':False})
    save(HERE/'collector-operator-approval.json',{**approval,'review_sha256':sha(HERE/'collector-operation-review.json'),'parent_review_sha256':sys.argv[1],'authority':'Actual parent approval explicitly includes this exact no-model conformance component; this is not a separate human answer.'})
    result={'review_sha256':sys.argv[1],'source_digest':review['source_digest'],'grant_before':before,'phases':[],'development_only':True,'formal_qualification':False,'admission':False,'efficacy_claim':False}
    try:
        for name,args,required in [('run-collector.py',[sha(HERE/'collector-operation-review.json')],'collector-result.json'),('assemble-collector-boundary.py',[],'boundary-result.json'),('run-model-journey.py',[sys.argv[1]],'model-result.json')]:
            began=time.perf_counter()
            with (HERE/(name+'.log')).open('x') as stream:
                completed=subprocess.run([sys.executable,str(HERE/name),*args],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,timeout=3000 if name=='run-model-journey.py' else 600)
            result['phases'].append({'script':name,'returncode':completed.returncode,'driver_wall_seconds':time.perf_counter()-began})
            assert completed.returncode==0 and (HERE/required).exists(),'Component failed; no retry or later model dispatch'
            observed=json.loads((HERE/required).read_text())
            if name=='run-collector.py':assert observed['passed'] and observed['proxy_restored_stopped'] and observed['source_unchanged']
            if name=='run-model-journey.py':assert observed['completed'] and observed['proxy_restored_stopped'] and observed['source_unchanged']
        result['development_journey_completed']=True
    except BaseException as exc:
        result.update(development_journey_completed=False,error_type=type(exc).__name__,error_message=str(exc)[:400])
    finally:
        router=Router.from_manifest(BASE/'aeep.json')
        try:after=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        finally:await router.close()
        result['grant_after']=after;result['operations_delta']=after[0]-before[0];result['model_turns_delta']=after[1]-before[1];result['charged_seconds_delta']=after[2]-before[2]
        result['review_counters_within_ceiling']=result['operations_delta']<=review['maximum_operations'] and result['model_turns_delta']<=6 and result['charged_seconds_delta']<=review['maximum_reserved_seconds'] and after[3]==before[3]
        result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];save(HERE/'execution-result.json',result)
        print(json.dumps(result))


if __name__=='__main__':asyncio.run(main())
