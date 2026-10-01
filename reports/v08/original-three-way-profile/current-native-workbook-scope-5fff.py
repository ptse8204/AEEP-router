"""Inert successor scope producer; enrollment requires an enclosing reviewed operation."""
import importlib.util,json
from datetime import timedelta
from pathlib import Path
from aeep.assessment.identity import file_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.models import ExecutorSpec,TaskScope,utc_now
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
PRODUCER=OUT/'current-native-workbook-producer.py'
PRODUCER_SHA='bc3369fdcdb5b86603b468395f7004b6a4fb3ae832c7eff54d991e0f98d910a7'
SNAPSHOT=OUT/'current-native-producer-setup-result.json'
SNAPSHOT_SHA='a17bdfdbb316d05a2231b311a16426d9aa11eec13e3e6fdd739625eecf619e67'
SCOPE_ID='current-composed-workbook-5fff'
def producer():
 if verification_source_digest(ROOT)!=SOURCE or file_digest(PRODUCER)!=PRODUCER_SHA or file_digest(SNAPSHOT)!=SNAPSHOT_SHA:
  raise ValueError('exact source/producer/original setup required')
 spec=importlib.util.spec_from_file_location('original_native_producer',PRODUCER)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module

def enroll():
 """One new authority in the same store; never setup, reset, or copy old allowance."""
 module=producer();original=json.loads(SNAPSHOT.read_text())
 router=module.Router.from_manifest(Path(original['project'])/'aeep.json')
 old_scope=TaskScope.model_validate(AssessmentRepository(router.store).get('task_scope','current-composed-workbook'))
 spec=router.registry.get('native.composed.workbook');native=module.NativeSandboxConfig.model_validate(spec.config['native_sandbox'])
 native.validate_single_process();native.argv([])
 try:
  if executor_fingerprint(spec)!=executor_fingerprint(ExecutorSpec.model_validate(original['spec'])) or old_scope.model_dump(mode='json')!=original['scope']:
   raise ValueError('original protected program/scope changed')
  repo=AssessmentRepository(router.store)
  with router.store._lock:
   if router.store._connection.execute('SELECT 1 FROM assessment_records WHERE kind=? AND id=?',('task_scope',SCOPE_ID)).fetchone():
    raise ValueError('successor scope already exists; no replay')
   if router.store._connection.execute("SELECT 1 FROM execution_attempts WHERE executor_id=? AND state IN ('CREATED','CLAIMED','RESERVED','INVOKING','VALIDATING','SETTLING','INDETERMINATE','DISPUTED') LIMIT 1",(spec.id,)).fetchone():
    raise ValueError('unresolved native attempt blocks enrollment')
  scope=old_scope.model_copy(update={'scope_id':SCOPE_ID,'expires_at':utc_now()+timedelta(hours=2)})
  digest=repo.put('task_scope',scope.scope_id,scope);repo.review(digest)
  router.bind_task_scope(scope.scope_id)
  return {'source_digest':SOURCE,'project':original['project'],'scope':scope.model_dump(mode='json'),'scope_digest':digest,'spec':spec.model_dump(mode='json'),'native':native.model_dump(mode='json'),'old_scope_preserved':True}
 finally:
  router.store.close()

def reopen():
 module=producer();original=json.loads(SNAPSHOT.read_text())
 router=module.Router.from_manifest(Path(original['project'])/'aeep.json')
 repo=AssessmentRepository(router.store);scope=TaskScope.model_validate(repo.get('task_scope',SCOPE_ID))
 spec=router.registry.get('native.composed.workbook');native=module.NativeSandboxConfig.model_validate(spec.config['native_sandbox'])
 if executor_fingerprint(spec)!=executor_fingerprint(ExecutorSpec.model_validate(original['spec'])) or scope.executor_fingerprints!={spec.id:executor_fingerprint(spec)} or scope.project_root!=original['project'] or scope.approval_ceiling.value!='read' or scope.max_attempts!=1 or scope.max_attempt_seconds!=10:
  router.store.close();raise ValueError('successor scope/program/ceiling drift')
 router.bind_task_scope(scope.scope_id)
 return module.services(router,scope,spec,native)
