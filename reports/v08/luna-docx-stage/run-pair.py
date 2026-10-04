"""One reviewed paired inspection; restore the existing proxy's prior stopped state."""
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import execute_pair
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).parent

def docker(*args, timeout=15):
    return subprocess.check_output(['docker',*args],text=True,timeout=timeout,stderr=subprocess.DEVNULL)

async def main():
    path=OUT/'pair-execution-review.json'
    if len(sys.argv)!=2 or hashlib.sha256(path.read_bytes()).hexdigest()!=sys.argv[1]:
        raise RuntimeError('exact review hash required')
    review=json.loads(path.read_text())
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=review['runner_sha256']:
        raise RuntimeError('runner changed')
    if verification_source_digest(ROOT)!=review['source_digest']:
        raise RuntimeError('source changed')
    pair_bytes=(OUT/'pair-review.json').read_bytes()
    if hashlib.sha256(pair_bytes).hexdigest()!=review['pair_review_sha256']:
        raise RuntimeError('pair review changed')
    pair_review=json.loads(pair_bytes)
    capacities=dict(line.split('=',1) for line in subprocess.check_output([sys.executable,str(OUT/'storage_probe.py')],text=True,timeout=10).splitlines())
    if int(capacities['NSURLVolumeAvailableCapacityForImportantUsageKey_bytes']) < 51*1024**3:
        raise RuntimeError('available capacity below reserve plus probe allowance')
    with (OUT/'pair-started.json').open('x') as f:
        json.dump({'review_sha256':sys.argv[1]},f)
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json')
    service=AssessmentService(router,ROOT/'.aeep/live-review-v3/.aeep/assessments');repo=service.repository
    request=ConformanceProbeRequest.model_validate(review['proxy_request'])
    operation=request.plan_id+':proxy_lifecycle'
    result={'source_digest':review['source_digest'],'request_ids':pair_review['request_ids'],
        'proxy_operation':operation,'model_turns':0,'qualification':False,'admission':False}
    started_proxy=False;reserved=False;began=time.monotonic()
    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
        repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=600,max_cash_usd=0),stage='reviewed_proxy_lifecycle')
        reserved=True
        meta=json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}',review['proxy_name']))
        if not meta['Id'].startswith(review['proxy_id_prefix']) or meta['Image']!=review['proxy_image']:
            raise RuntimeError('existing proxy identity differs')
        if review['network_id'] not in [v['NetworkID'] for v in meta['Networks'].values()]:
            raise RuntimeError('existing proxy network differs')
        result['proxy_was_running']=meta['Running']
        if not meta['Running']:
            repo.authorize(request)
            started_proxy=True
            docker('start',review['proxy_name'])
        async with asyncio.timeout(420):
            pair=await execute_pair(service,*pair_review['request_ids'])
        result['pair']=pair;workers={}
        for role in ('control','treatment'):
            record=repo.get('worker_pair_inspection',pair['workers'][role]['record_digest'])
            observations=record['observations'];inspection=observations.get('inspection',{})
            models=[m for m in inspection.get('models',[]) if m.get('id')=='gpt-6-luna']
            workers[role]={'cleanup_confirmed':observations.get('cleanup_confirmed'),
                'identity_digest':inspection.get('identity_digest'),'luna_present':len(models)==1,
                'xhigh_present':len(models)==1 and 'xhigh' in models[0].get('reasoning_efforts',[]),
                'failed_stage':inspection.get('failed_stage'),'error_type':inspection.get('error_type')}
        result['workers']=workers
        result['paired_checks_passed']=bool(pair.get('probes_match')) and all(
            v['cleanup_confirmed'] and v['identity_digest'] and v['luna_present'] and v['xhigh_present'] for v in workers.values())
    except BaseException as exc:
        result.update(paired_checks_passed=False,error_type=type(exc).__name__)
    finally:
        if started_proxy:
            try:
                docker('stop','--time','5',review['proxy_name'],timeout=20)
                result['proxy_restored_stopped']=docker('inspect','--format','{{.State.Running}}',review['proxy_name']).strip()=='false'
            except Exception as exc:
                result.update(proxy_restored_stopped=False,proxy_cleanup_error_type=type(exc).__name__)
        elapsed=time.monotonic()-began
        if reserved:repo.finish_operation(operation,elapsed_seconds=elapsed)
        result.update(proxy_lifecycle_wall_seconds=elapsed,source_unchanged=verification_source_digest(ROOT)==review['source_digest'],
            full_conformance=False,replay_allowed=False)
        row=router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()
        result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row))
        (OUT/'pair-result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result));await router.close()

asyncio.run(main())
