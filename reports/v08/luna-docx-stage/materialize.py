"""Prepare or execute one contained 8/28/105 DOCX case generation; no answers printed."""
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from aeep.assessment.extensions import prepare, materialize
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='060fbefd55ff1c73256520a0c1e3d0de0e029755b75437cf7a93d7b68335e293'
async def main():
    if verification_source_digest(ROOT)!=SOURCE:raise RuntimeError('source drift')
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json')
    service=AssessmentService(router,ROOT/'.aeep/live-review-v3/.aeep/assessments');repo=service.repository
    try:
        path=OUT/'materialization-review.json'
        if len(sys.argv)==1:
            if path.exists():raise RuntimeError('preserve existing request')
            setup=json.loads((OUT/'setup-review.json').read_text())
            sd=setup['request']['subject_digest'];rd=setup['request']['recipe_digest']
            environment=AssessmentEnvironment(environment_id='skillsbench-docx-cases-20261002',kind='container',
                identity={'purpose':'Protected qualification case generation; no worker or model'},
                container_image='sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',
                container_runtime=shutil.which('docker'),container_socket=str(Path.home()/'.docker/run/docker.sock'),
                memory_mb=256,process_limit=64)
            request=prepare(service,subject_id=sd,recipe_id=rd,authorization_id='onboarding',environment=environment,seed=2026100202)
            definitions={sd:repo.get('subject',sd),rd:repo.get('recipe',rd),content_digest(environment):environment.model_dump(mode='json'),
                content_digest(request):request.model_dump(mode='json')}
            for digest in request.definition_digests:
                if digest not in definitions:definitions[digest]=repo.get('recipe_runtime',digest)
            original=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
            amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(original),
                subject_digests=[sd],recipe_digests=[rd],environment_digests=[content_digest(environment)],reviewed_digests=list(definitions))
            database_bytes=router.store._connection.execute('PRAGMA page_count').fetchone()[0]*router.store._connection.execute('PRAGMA page_size').fetchone()[0]
            review={'authority':'September25/27 finite exact scope delegation; fresh SkillsBench qualification inputs',
                'source_digest':SOURCE,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'request':request.model_dump(mode='json'),'definitions':definitions,'amendment':amendment.model_dump(mode='json'),
                'maximum_operations':1,'maximum_seconds':35,'maximum_model_turns':0,'cash_usd':0,
                'measured_database_bytes':database_bytes,'storage_allowance_bytes':2*database_bytes+100_000_000,
                'split_counts':{'qualification':8,'training':28,'holdout':105},'seed':2026100202,
                'no_cases_in_worker_images':True,'no_admission_or_trial_execution':True,'approval_committed':False}
            path.write_text(json.dumps(review,indent=2)+'\n')
            print(json.dumps({'request_id':request.plan_id,'review_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}));return
        if len(sys.argv)!=2 or hashlib.sha256(path.read_bytes()).hexdigest()!=sys.argv[1]:raise RuntimeError('exact review hash required')
        review=json.loads(path.read_text())
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=review['runner_sha256']:raise RuntimeError('runner changed')
        capacities=dict(line.split('=',1) for line in subprocess.check_output([sys.executable,str(OUT/'storage_probe.py')],text=True,timeout=10).splitlines())
        if int(capacities['NSURLVolumeAvailableCapacityForImportantUsageKey_bytes']) < 50*1024**3+review['storage_allowance_bytes']:raise RuntimeError('available storage insufficient')
        with (OUT/'materialization-started.json').open('x') as f:json.dump({'review_sha256':sys.argv[1]},f)
        result={'source_digest':SOURCE,'request_id':review['request']['plan_id'],'model_turns':0,'replay_allowed':False}
        try:
            repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
            cases=await materialize(service,result['request_id'])
            counts={name:sum(c.split.value==name for c in cases.cases) for name in ('qualification','training','holdout')}
            result.update(case_set_digest=content_digest(cases),case_count=len(cases.cases),split_counts=counts,
                distinct_inputs=len({content_digest(c.input) for c in cases.cases}))
            if counts!=review['split_counts'] or result['distinct_inputs']!=141:raise RuntimeError('case contract mismatch')
            result['materialization_passed']=True
        except BaseException as exc:result.update(materialization_passed=False,error_type=type(exc).__name__)
        result['source_unchanged']=verification_source_digest(ROOT)==SOURCE
        row=router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()
        result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row))
        (OUT/'materialization-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:await router.close()
asyncio.run(main())
