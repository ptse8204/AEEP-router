"""Immutable evidence successor from the retained raw host journal; no execution."""
import asyncio,json
from pathlib import Path
from aeep.router import Router
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.models import content_digest
from aeep.assessment.boundary import BoundaryProbe
from aeep.execution import EventJournal,ExecutionEvidence
from aeep.models import ExecutionReceipt,ExecutionStatus,RawExecution
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
OLD_PROBE='composed-probe_c1c049cca338422ba2077efa980cc3a4'
RAW='f4126c61ffa13841b4a199ca59a72cd09897528d59018683e027f828cbe7df32'
HOST='946050ca8b65b01f032c0e6c44cd0a09532aa60951a1445d66225c202acd18b9'
async def main():
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');q=AssessmentRepository(r.store)
 try:
  old=BoundaryProbe.model_validate(q.get('boundary_probe',OLD_PROBE));receipt=ExecutionReceipt.model_validate(q.get('conformance_host_receipt',HOST));raw=ExecutionEvidence.model_validate(q.get('execution_evidence',RAW))
  observation=q.get('composed_runner_result','composed:conformance_current_composed_ready_ade3')
  if (content_digest(raw)!=RAW or content_digest(receipt)!=HOST or old.host_receipt_digest!=HOST or receipt.metadata.get('execution_evidence_digest')!=RAW or not raw.complete or receipt.status is not ExecutionStatus.SUCCESS or observation['cleanup_confirmed'] is not True):raise ValueError('actual retained host/cleanup binding differs')
  with q.store._lock:
   row=q.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?',(observation['operation_id'],)).fetchone()
  if row is None or row[0]!='complete':raise ValueError('inclusive original operation not complete')
  journal=EventJournal(raw.attempt_id)
  for event in raw.events:
   if event.kind in {'execution.completed','execution.failed'}:continue
   journal.append(event.kind,event.source_id,action_digest=event.action_digest,evidence_ref=event.evidence_ref,accounting=event.accounting,accounting_mode=event.accounting_mode)
  journal.append('artifact.created','composed-observation',evidence_ref=content_digest(old.observed));journal.append('execution.completed','composed-terminal')
  evidence=journal.evidence(raw.adapter,RawExecution(status=receipt.status,metadata={'host_runtime_digest':raw.identity_digest,'boundary_digest':raw.boundary_digest}))
  digest=q.put('execution_evidence',content_digest(evidence),evidence)
  probe=old.model_copy(update={'probe_id':'composed-probe-current-raw-journal-successor','execution_evidence_digest':digest})
  q.put('boundary_probe',probe.probe_id,probe)
  record={'original_probe':old.model_dump(mode='json'),'original_raw_evidence_digest':RAW,'successor_probe':probe.model_dump(mode='json'),'successor_evidence_digest':digest,'derivation':'Original raw event source identities retained unchanged; same payload-free controller observation/terminal added after confirmed original cleanup/accounting. Double-prefix original preserved.','new_model_turns':0,'new_native_attempts':0,'full_conformance':False}
  (OUT/'current-composed-callback-evidence-successor.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'successor_probe':probe.probe_id,'successor_evidence_digest':digest,'model_turns':0,'native_attempts':0}))
 finally:await r.close()
asyncio.run(main())
