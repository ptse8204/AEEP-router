from pathlib import Path
import ast,base64,copy,hashlib,json,shutil
from aeep.assessment.models import AssessmentEnvironment,AssessmentSubject,ExecutableRecipeExtension,RecipeDefinition,RecipeLiteralFixture,RecipeFeatureRule,AssessmentScopeAmendment,AssessmentAuthorization,content_digest
from aeep.assessment.extensions import prepare
from aeep.assessment.service import AssessmentService
from aeep.router import Router
from aeep.models import ExecutorSpec,ExecutorKind,SideEffect
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
assets=ROOT/'reports/v08/skillsbench-offer-letter-pinned'
template=base64.b64encode((assets/'offer_letter_template.docx').read_bytes()).decode();data=json.loads((assets/'employee_data.json').read_text());value={'template_b64':template,'employee_data':data}
source=(ROOT/'tests/test_v08_skillsbench_offer_letter.py').read_text();tree=ast.parse(source);builder=next(ast.get_source_segment(source,n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_filled')
ns={};exec('import base64,io,re,zipfile\nfrom xml.etree import ElementTree as ET\nW="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"\n'+builder,ns)
correct={'document_b64':ns['_filled'](base64.b64decode(template),data)}
faults=[{'document_b64':template},{'document_b64':ns['_filled'](base64.b64decode(template),data,remove_paragraph=True)},{'document_b64':'!!!'}]
fixtures={'input':value,'truth':value,'correct':correct,'faults':faults,'expected_grader_decisions':[True,False,False,False]}
(OUT/'fixtures.json').write_text(json.dumps(fixtures,ensure_ascii=False)+'\n')
input_schema={'type':'object','required':['template_b64','employee_data'],'additionalProperties':False,'properties':{'template_b64':{'type':'string','maxLength':200000},'employee_data':{'type':'object','additionalProperties':{'type':'string'}}}}
output_schema={'type':'object','additionalProperties':False,'required':['document_b64'],'properties':{'document_b64':{'type':'string','maxLength':200000}}}
def spec(name,code):return ExecutorSpec(id='skillsbench.'+name,capability='assessment.skillsbench_'+name+'@1',kind=ExecutorKind.COMMAND,description='Protected exploratory '+name,side_effect=SideEffect.READ,idempotent=True,config={'argv':['python3','-I','-c',code],'argv_literal':True,'stdin_json':True,'output':{'type':'json'},'timeout_seconds':30,'max_output_bytes':2000000})
variant=copy.deepcopy(value);variant['employee_data']['CANDIDATE_FULL_NAME']='Reviewed Fixture Name'
extension=ExecutableRecipeExtension(schema_version='assessment.recipe-extension.v2',generator=spec('generator','raise RuntimeError("Exploratory only: qualifying materialization is unsupported")'),grader=spec('grader',(OUT/'grader.py').read_text()),reference=spec('reference',(OUT/'reference.py').read_text()),independent_fixtures=[RecipeLiteralFixture(input=value,output=value),RecipeLiteralFixture(input=variant,output=variant)],transformed_fixtures=[RecipeLiteralFixture(input=value,output=value)],fault_outputs=faults,feature_rules={'relocation':RecipeFeatureRule(path='/employee_data/RELOCATION_PACKAGE',operation='enum',values=['Yes'])},variation_features={'pinned_yes':{'relocation':'Yes'}},template_families=['pinned_offer_letter'],truth_schema=input_schema)
recipe=RecipeDefinition(schema_version='assessment.recipe.v2',recipe_id='skillsbench-offer-letter-exploratory-handoff',capability='assessment.offer_letter@1',description='ONE adapted pinned task protected artifact handoff; no upstream verifier, materialization, qualification or admission',input_schema=input_schema,output_schema=output_schema,generator='contained_json:1',grader='contained_json:1',extractor='structural_json:1',variations=['pinned_yes'],extension=extension)
subject=AssessmentSubject(kind='command',location=str(OUT/'reference.py'),dependency_digests={'reference':hashlib.sha256((OUT/'reference.py').read_bytes()).hexdigest()},description='Exploratory local artifact reference only')
env=AssessmentEnvironment(environment_id='skillsbench-protected-offline-existing',kind='container',identity={'purpose':'protected exploratory artifact handoff'},container_image='aeep-assessment-runtime@sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',container_runtime=shutil.which('docker'),container_socket=str(Path.home()/'.docker/run/docker.sock'),memory_mb=256,process_limit=64)
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');service=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');repo=service.repository
try:
 definitions={}
 for kind,obj,ident in [('subject',subject,subject.subject_id),('recipe',recipe,recipe.recipe_id),('environment',env,env.environment_id)]:definitions[repo.put(kind,ident,obj)]=obj
 request=prepare(service,subject_id=subject.subject_id,recipe_id=recipe.recipe_id,authorization_id='onboarding',environment=env,seed=20260930)
 for digest in request.definition_digests:
  if digest not in definitions:definitions[digest]=repo.get('recipe_runtime',digest)
 request_digest=content_digest(request);definitions[request_digest]=request
 grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
 amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[content_digest(subject)],recipe_digests=[content_digest(recipe)],environment_digests=[content_digest(env)],reviewed_digests=list(definitions))
 review={'authority':'Standing finite amendment delegation; parent authorized exact one exploratory protected handoff September30','executed':False,'request':request.model_dump(mode='json'),'request_digest':request_digest,'amendment':amendment.model_dump(mode='json'),'definitions':{d:o.model_dump(mode='json') if hasattr(o,'model_dump') else o for d,o in definitions.items()},'maximum_operations':2,'maximum_reserved_seconds':70,'model_turns':0,'cash':0,'fixture_sha256':hashlib.sha256((OUT/'fixtures.json').read_bytes()).hexdigest(),'expected_grader_decisions':[True,False,False,False],'no_admission':True,'no_materialize':True,'budget':'Existing main onboarding counters/ceilings unchanged;2 invoke reservations at35s each only after quiet window. No budget increase needed.'}
 (OUT/'review.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps({'request_id':request.plan_id,'request_digest':request_digest,'review_sha256':hashlib.sha256((OUT/'review.json').read_bytes()).hexdigest(),'approval_committed':False}))
finally:r.store.close()
