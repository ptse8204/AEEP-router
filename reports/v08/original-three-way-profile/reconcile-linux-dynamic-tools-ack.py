"""Read-only reconstruction of terminal ACK evidence; never launches a worker."""
import hashlib,json,sqlite3
from decimal import Decimal
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).parent
review=json.loads((OUT/'linux-dynamic-tools-ack-review.json').read_text())
operation='linux-dynamic-tools-ack:'+review['requests'][0]['plan_id']
manifest=json.loads((ROOT/'.aeep/live-review-v3/aeep.json').read_text())
c=sqlite3.connect('file:'+manifest['database']+'?mode=ro',uri=True)
rows=c.execute("SELECT digest,payload_json FROM assessment_records WHERE kind='linux_task_boundary_observation'").fetchall()
digest,document=next((d,json.loads(p)) for d,p in rows if json.loads(p)['facts']['operation_id']==operation)
measurement=json.loads(c.execute("SELECT payload_json FROM assessment_records WHERE kind='operation_measurement' AND id=?",(operation,)).fetchone()[0])
state=c.execute('SELECT state,reserved_json FROM assessment_operations WHERE id=?',(operation,)).fetchone();assert state[0]=='complete'
limits=json.loads(state[1]); counters=c.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()
result={'source_digest':review['source_digest'],'source_unchanged':verification_source_digest(ROOT)==review['source_digest'],'reconstructed':True,'runtime_result':document['facts'],'canonical_observation_digest':digest,'operation_measurement':measurement,'operation_state':state[0],'reporting_error':{'type':'TypeError','stage':'final accounting_delta','cause':'cash_usd is a decimal string; subtraction requires Decimal conversion','launched_driver_sha256':review['driver_sha256'],'failure_log_sha256':hashlib.sha256((OUT/'linux-dynamic-tools-ack-execution.log').read_bytes()).hexdigest()},'grant_before':None,'grant_before_status':'not persisted by launched driver; not reconstructed from aggregate counters','grant_after':dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),counters)),'operation_charge':{'operations':limits['max_operations'],'model_turns':limits['max_model_turns'],'elapsed_seconds':measurement['elapsed_seconds'],'cash_usd':str(Decimal(limits['max_cash_usd']))},'classification':'transport_initialization_failed; dynamic declaration support not tested','runtime_version':'unknown initialization failed','model_turns':0,'dynamic_calls':0,'full_conformance':False,'release_ready':False,'replay_allowed':False,'argv':review['definition']['profiles']['outside_mcp']['config']['argv'],'executed_command':['python3','reports/v08/original-three-way-profile/run-linux-dynamic-tools-ack-inert.py',hashlib.sha256((OUT/'linux-dynamic-tools-ack-review.json').read_bytes()).hexdigest()]}
c.close();(OUT/'linux-dynamic-tools-ack-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'cleanup_confirmed':result['runtime_result']['cleanup_confirmed'],'failed_stage':result['runtime_result']['failing_stage'],'source_unchanged':result['source_unchanged'],'operation_charge':result['operation_charge']}))
