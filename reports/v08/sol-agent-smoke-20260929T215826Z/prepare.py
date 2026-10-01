import asyncio,base64,hashlib,json,subprocess,sys
from datetime import timedelta,datetime,timezone
from pathlib import Path
from aeep.assessment.workbook import workbook_recipe
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import Manifest,TaskScope,SideEffect,utc_now
from aeep.router import Router
from aeep.tasks import activate
root=Path.cwd()
run=root/'reports/v08'/('sol-agent-smoke-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
project=run/'project';project.mkdir(parents=True)
assets=root/'integrations/assessment-runtime'
python=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
prefix=subprocess.run([str(python),'-I','-c','import sys;print(sys.prefix)'],capture_output=True,text=True,check=True).stdout.strip()
cases=json.loads(subprocess.run([str(python),'-I',str(assets/'workbook_program.py'),'generate'],input=json.dumps({'seed':20260930,'stages':[{'split':'exploratory','count':11}]}),capture_output=True,text=True,check=True).stdout)['cases']
binary=Path('/Users/edwintse/.local/bin/codex').resolve()
boundary=NativeSandboxConfig(binary=str(binary),binary_sha256='sha256:'+hashlib.sha256(binary.read_bytes()).hexdigest(),project_root=str(project),read_roots=[prefix])
recipe=workbook_recipe();spec=recipe.extension.reference.model_copy(deep=True)
spec.id='native.workbook.reference';spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema
source=(assets/'workbook_program.py').read_text()
program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);print(json.dumps(ns['reference'](json.load(sys.stdin))))"
spec.config={**spec.config,'argv':[str(python),'-I','-c',program],'native_sandbox':boundary.model_dump(mode='json'),'max_output_bytes':200000}
manifest=project/'aeep.json';manifest.write_text(Manifest(database=str(project/'.aeep/state.db'),executors=[spec]).model_dump_json(indent=2))
async def prepare():
 router=Router.from_manifest(manifest)
 try:
  repo=AssessmentRepository(router.store);repo.review(repo.put('recipe',recipe.recipe_id,recipe))
  scope=TaskScope(scope_id='sol-exploratory',project_root=str(project),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.READ,max_attempts=2,max_attempt_seconds=30,expires_at=utc_now()+timedelta(minutes=30))
  digest=repo.put('task_scope',scope.scope_id,scope);repo.review(digest)
  activation=activate(router,scope.scope_id)
  return activation.activation_id,digest
 finally: await router.close()
activation,digest=asyncio.run(prepare())
selected=[]
for label,index in [('small',0),('larger',10)]:
 case=cases[index];(project/(label+'-input.json')).write_text(json.dumps(case['input']))
 (project/(label+'-input.xlsx')).write_bytes(base64.b64decode(case['input']['workbook_b64']))
 selected.append({'label':label,'case_index':index,'expected':case['output']})
(run/'private-expected.json').write_text(json.dumps(selected))
record={'kind':'exploratory live subagent integration smoke; not a controlled comparison or qualification','model_requested':'gpt-6-sol','source_digest':verification_source_digest(root),'project':str(project),'manifest':str(manifest),'activation_id':activation,'scope_digest':digest,'tool_name':'aeep_recipe_'+hashlib.sha256(recipe.capability.encode()).hexdigest()[:12],'max_task_attempts':2,'per_task_seconds':30,'seed':20260930,'cases':[0,10],'authority':'User explicitly requested GPT-6 Sol sub-agent real test; standing finite test-definition delegation. Zero paid API calls, no global configuration changes.','shared_filesystem_limit':'Subagent instructions restrict file access; this is not an enforced isolated benchmark worker.','checks':['task output independently graded','receipt validity and explanations','pause rejection','unknown capability rejection','allowance exhaustion','uninstall accounting retained']}
(run/'plan.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record,indent=2))
