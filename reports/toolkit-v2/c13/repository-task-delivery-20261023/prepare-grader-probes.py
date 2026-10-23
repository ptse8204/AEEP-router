"""Prepare fresh current-source grader boundary probes; execute no subject software."""
import hashlib
import json
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment,AssessmentScopeAmendment,AssessmentSubject,RecipeDefinition,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.repository_suites import archive_files,pack_files
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router
import base64

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
parent_path=HERE.parent/'repository-workload-batch-20261022/runtime-execution/parent-runtime-review.json'
parent=json.loads(parent_path.read_text());proposal=json.loads((HERE/'collector-definitions.json').read_text())
recipe=RecipeDefinition.model_validate(proposal['definitions'][proposal['requests'][0]['recipe_digest']])
canary=ROOT/'.aeep/repository-task-delivery-20261023/host-canary';assert not canary.exists()
probes=json.loads(json.dumps(parent['probes']))
for item in probes:
    payload=item['payload'];files=archive_files(base64.b64decode(payload['archive']))
    files={name:data.replace(str(ROOT/parent['host_canary']).encode(),str(canary).encode()) for name,data in files.items()}
    archive=pack_files(files);payload['archive']=base64.b64encode(archive).decode();payload['archive_sha256']=hashlib.sha256(archive).hexdigest()
    item['archive_sha256']=payload['archive_sha256'];item['payload_sha256']=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
(HERE/'grader-probes.json').write_text(json.dumps(probes,indent=2)+'\n')
environment=AssessmentEnvironment(environment_id='repository-task-delivery-grader-'+proposal['source_digest'][:12],kind='container',identity={'source_digest':proposal['source_digest'],'purpose':'Fresh grader boundary/state probes only'},container_image=parent['image'],container_runtime=parent['docker'],container_socket=parent['socket'].removeprefix('unix://'),memory_mb=512)
runtime=RecipeRuntimeBinding(dependencies=runtime_dependencies())
subject=AssessmentSubject(kind='command',location=str(HERE.resolve()),dependency_digests={str((HERE/'grader-probes.json').resolve()):hashlib.sha256((HERE/'grader-probes.json').read_bytes()).hexdigest()},description='Three fixed runtime boundary/state probes; no candidate or repository task outcome.')
request=RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',subject_digest=content_digest(subject),recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=content_digest(environment),authorization_id='onboarding',seed=73,definition_digests=[content_digest(recipe),content_digest(environment),content_digest(runtime)],runtime_dependencies=runtime.dependencies)
documents={content_digest(value):{'kind':kind,'id':identity,'document':value.model_dump(mode='json')} for kind,identity,value in [('subject',subject.subject_id,subject),('recipe',recipe.recipe_id,recipe),('environment',environment.environment_id,environment),('recipe_runtime',content_digest(runtime),runtime),('recipe_materialization_request',request.plan_id,request)]}
router=Router.from_manifest(BASE/'aeep.json')
try:
    before=tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone());repo=AssessmentService(router,BASE/'.aeep/assessments').repository
    for digest,item in documents.items():
        cls={'subject':AssessmentSubject,'recipe':RecipeDefinition,'environment':AssessmentEnvironment,'recipe_runtime':RecipeRuntimeBinding,'recipe_materialization_request':RecipeMaterializationRequest}[item['kind']]
        assert repo.put(item['kind'],item['id'],cls.model_validate(item['document']))==digest
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(repo.get('authorization','onboarding')),subject_digests=[content_digest(subject)],recipe_digests=[content_digest(recipe)],environment_digests=[content_digest(environment)],reviewed_digests=list(documents))
    assert before==tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
finally:router.store.close()
result={'source_digest':verification_source_digest(ROOT),'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':hashlib.sha256(parent_path.read_bytes()).hexdigest(),'request':request.model_dump(mode='json'),'documents':documents,'amendment':amendment.model_dump(mode='json'),'canary':str(canary),'canary_text':'AEEP public nonsecret task-delivery containment marker\n','maximum_operations':5,'maximum_reserved_seconds':165,'maximum_grader_calls':3,'actual_executions':0,'grant_counters_unchanged':True}
(HERE/'grader-probe-definitions.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'prepared_probes':3,'source_digest':result['source_digest'],'grant_counters_unchanged':True,'untrusted_execution':False}))
