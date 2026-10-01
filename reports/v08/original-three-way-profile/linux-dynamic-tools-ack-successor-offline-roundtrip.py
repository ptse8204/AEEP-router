import ast,json,sqlite3,tempfile,hashlib,os
from pathlib import Path
from aeep.store import ReceiptStore
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.models import AssessmentScopeAmendment,ConformanceProbeRequest,content_digest
from aeep.models import StrictModel
root=Path.cwd();out=root/'reports/v08/original-three-way-profile';review=json.loads((out/'linux-dynamic-tools-ack-successor-review.json').read_text())
source=sqlite3.connect('file:'+str(root/'.aeep/live-review-v3/aeep.sqlite3')+'?mode=ro',uri=True)
# Obtain only existing assessment authority and the exact three referenced definitions.
tree=ast.parse((out/'run-linux-dynamic-tools-ack-successor-inert.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Definition');scope={'StrictModel':StrictModel};exec(compile(ast.Module(body=[node],type_ignores=[]),'owned-definition','exec'),scope);Definition=scope['Definition']
with tempfile.TemporaryDirectory(prefix='aeep-ack-roundtrip-') as td:
 store=ReceiptStore(Path(td)/'state.db');repo=AssessmentRepository(store)
 refs=[review['requests'][0][k] for k in ('subject_digest','recipe_digest','environment_digest')]
 conn=store._connection
 rows=source.execute('SELECT * FROM assessment_records WHERE kind IN (?,?,?) OR digest IN (?,?,?)',('authorization','budget_amendment','scope_amendment',*refs)).fetchall()
 conn.executemany('INSERT OR IGNORE INTO assessment_records VALUES (?,?,?,?)',rows)
 for table in ('assessment_grants','assessment_budget_amendments'):
  if source.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
   records=source.execute('SELECT * FROM '+table).fetchall()
   if records:conn.executemany('INSERT OR REPLACE INTO '+table+' VALUES ('+','.join('?' for _ in records[0])+')',records)
 conn.commit()
 before=conn.execute('SELECT * FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()
 definition=Definition.model_validate(review['definition']);assert definition.model_dump(mode='json')==review['definition'];assert repo.put('linux_task_probe_definition',review['definition_digest'],definition)==review['definition_digest']
 request=ConformanceProbeRequest.model_validate(review['requests'][0]);repo.put('conformance_request',request.plan_id,request)
 repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions']);repo.authorize(request)
 assert repo.get('linux_task_probe_definition',review['definition_digest'])==review['definition']
 assert conn.execute('SELECT * FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()==before
 store.close()
source.close();print('Exact typed definition/register/approve/authorize roundtrip PASS; grant counters unchanged; owned temporary store removed.')
