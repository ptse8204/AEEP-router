"""Operator-owned concrete protected workbook producer; import starts nothing."""
import copy,hashlib,json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.workbook import workbook_recipe
from aeep.assessment.workbook_native import implementation_digest
from aeep.assessment.fixed_helper import FixedHelperService
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.hosts.codex_invocation import contract_digest
from aeep.hosts.codex_sandbox import NativeSandboxConfig,native_backend_digest
from aeep.models import Manifest,PolicyConfig,FallbackConfig,TaskScope,SideEffect,ExecutorKind,ValidationSpec,ValidationKind,utc_now
from aeep.mcp.server import AEEPToolService
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[3]
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def require_pins():
 if sha(BINARY)!='50ac633af64851511f9bbc71032cdae7f1ba20b3234c189687d61ba846c354c5':raise ValueError('native binary pin changed')
def setup(project):
 """One fresh durable scope, reviewed under the enclosing finite setup operation."""
 require_pins()
 project=Path(project).resolve()
 if project.exists():raise ValueError('owned fresh project required; no allowance reset')
 project.mkdir();scratch=project/'scratch';scratch.mkdir()
 native=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+sha(BINARY),
  project_root=str(project),read_roots=[str(PYTHON.parent.parent),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],
  deny_roots=[str(project/'.aeep'),str(project/'aeep.json')],single_process=True,
  python_binary=str(PYTHON),python_sha256='sha256:'+sha(PYTHON))
 recipe=workbook_recipe();spec=recipe.extension.reference.model_copy(deep=True)
 source=(ROOT/'integrations/assessment-runtime/workbook_program.py').read_text()
 program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);inp=json.load(sys.stdin);print(json.dumps(ns['reference'](inp)))"
 spec.id='native.composed.workbook';spec.kind=ExecutorKind.COMMAND
 spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema
 spec.config={'argv':[str(PYTHON),'-I','-c',program],'argv_literal':True,'stdin_json':True,'max_output_bytes':200000,
  'timeout_seconds':10,'output':{'type':'json'},'env':{'TMPDIR':str(scratch)},'native_sandbox':native.model_dump(mode='json')}
 spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'aeep.workbook.native.v1','implementation_digest':implementation_digest()})]
 manifest=Manifest(database=str(project/'.aeep/state.db'),executors=[spec],policies={'balanced':PolicyConfig(fallback=FallbackConfig(enabled=False,max_attempts=1))})
 path=project/'aeep.json';path.write_text(manifest.model_dump_json());router=Router.from_manifest(path)
 repo=AssessmentRepository(router.store);repo.review(repo.put('recipe',recipe.recipe_id,recipe))
 scope=TaskScope(scope_id='current-composed-workbook',project_root=str(project),executor_fingerprints={spec.id:executor_fingerprint(spec)},
  approval_ceiling=SideEffect.READ,max_attempts=1,max_attempt_seconds=10,expires_at=utc_now()+timedelta(hours=2))
 digest=repo.put('task_scope',scope.scope_id,scope);repo.review(digest);router.bind_task_scope(scope.scope_id)
 return services(router,scope,spec,native)

def reopen(project):
 require_pins()
 project=Path(project).resolve();router=Router.from_manifest(project/'aeep.json')
 repo=AssessmentRepository(router.store);scope=TaskScope.model_validate(repo.get('task_scope','current-composed-workbook'))
 spec=router.registry.get('native.composed.workbook');native=NativeSandboxConfig.model_validate(spec.config['native_sandbox'])
 if scope.project_root!=str(project) or scope.executor_fingerprints!={spec.id:executor_fingerprint(spec)}:raise ValueError('stored scope/manifest changed')
 router.bind_task_scope(scope.scope_id)
 return services(router,scope,spec,native)

def services(router,scope,spec,native):
 repo=AssessmentRepository(router.store);digest=content_digest(scope)
 def scope_check():
  router._require_active_spec(spec)
  current=TaskScope.model_validate(repo.get('task_scope',router._task_scope_digest))
  if content_digest(current)!=digest or current.executor_fingerprints!={spec.id:executor_fingerprint(router.registry.get(spec.id))}:
   raise ValueError('protected scope/code changed')
  return digest
 aeep=AEEPToolService(router,profile='task',task_scope=scope.scope_id)
 expected_name='aeep_recipe_'+hashlib.sha256(spec.capability.encode()).hexdigest()[:12]
 matches=[tool for tool in aeep.list_tools() if tool['name']==expected_name and tool['inputSchema']==spec.input_schema]
 if len(matches)!=1:raise ValueError('exact workbook declaration required')
 declaration=copy.deepcopy(matches[0]);declaration['name']='fixed_workbook';declaration['description']='Fixed reviewed workbook helper; no selection/ranking.'
 fixed=FixedHelperService(router,spec.id,task_scope=scope.scope_id,declaration=declaration,check=scope_check)
 return router,scope,spec,native,fixed,aeep

def document(services,worker,artifact,scope,spec,native):
 """Freeze actual service declarations with the existing artifact wrapper."""
 identity={'worker_digest':worker.digest(),'native_backend_digest':contract_digest({spec.id:native_backend_digest(native)}),
  'implementation_digest':CodexDynamicTools.implementation_digest(),'approval_ceiling':'read',
  'executor_fingerprints':scope.executor_fingerprints,'scope_limits':{'max_attempts':1,'max_attempt_seconds':10.0},
  'artifact':artifact.model_dump(mode='json')}
 context=SimpleNamespace(config=SimpleNamespace(artifact=artifact),request=SimpleNamespace(input={}))
 declarations=[]
 for service in services:
  # This only constructs declarations; neither verifier nor handler is invoked.
  inner=CodexDynamicTools.task_service(service,namespace='workbook',identity=identity,max_calls=1,timeout_seconds=10.0,
   check=lambda: content_digest(TaskScope.model_validate(AssessmentRepository(service.router.store).get('task_scope',service.router._task_scope_digest))),artifact_context=context,artifact_worker=worker,execution_id='declaration-only')
  declarations.extend(inner.definition()['tools'])
 return {'namespace':'workbook','tools':declarations,'identity':identity,'max_calls':1,'timeout_seconds':10.0}
