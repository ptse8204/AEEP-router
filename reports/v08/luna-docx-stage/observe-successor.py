"""Read current canonical trial summaries; never expose task inputs or outputs."""
import json,sqlite3
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
PLAN='plan_b3ccf1dccc4043129ad213eb7a50e6d4'
path=ROOT/'.aeep/live-review-v3/.aeep/assessments'/PLAN/'campaign.sqlite3'
connection=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
try:trials=[json.loads(row[0]) for row in connection.execute('SELECT payload_json FROM trials')]
finally:connection.close()
rows=[{key:trial.get(key) for key in ('trial_id','phase','state','started_at','ended_at','ok','valid','correctness_failed','wall_time_ms','failure_category','failure_stage','error_type','model_usage_complete','operation_count','retry_fallback_count','intervention_count')} for trial in trials]
summary={'observed_at':datetime.now(timezone.utc).isoformat(),'plan_id':PLAN,'assessment_id':'assessment_b7304a6d072c4aae98e45839200e9055','states':dict(Counter(x['state'] for x in rows)),'passed_by_phase':dict(Counter(x['phase'] for x in rows if x['ok'] and x['valid'] is True)),'correctness_failures_by_phase':dict(Counter(x['phase'] for x in rows if x['correctness_failed'] is True)),'qualification_failure_observed':any(x['correctness_failed'] is True for x in rows),'assigned_total':141,'trials':rows,'process_liveness':'Check PTY session37153 separately; stored running state alone is insufficient.','qualification_claimed':False,'admission_claimed':False,'comparative_benefit_claimed':False}
(OUT/'successor-progress.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='trials'}))
