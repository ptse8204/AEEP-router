"""Audit only synthetic task-owned evidence; never inspect host authentication."""
import json,shutil,sqlite3,subprocess,tempfile
from pathlib import Path
from verify_controlled import verify
ROOT=Path(__file__).resolve().parent
retained=ROOT/'retained-output'
private=ROOT/'private-output'
assert verify(retained)['verified_trials']==6
assert verify(private)['outputs_retained'] is False
results=[]
for attack in ('summary','artifact','receipt','event','ledger','retention'):
 with tempfile.TemporaryDirectory(prefix='aeep-c06-verifier-') as name:
  copied=Path(name)/'evidence'
  shutil.copytree(retained,copied)
  if attack=='artifact':next((copied/'upstream').rglob('output.txt')).write_text('altered')
  elif attack in ('receipt','event'):
   db=sqlite3.connect(copied/'receipts.sqlite3')
   db.execute("UPDATE receipts SET payload_json='{}'" if attack=='receipt' else "DELETE FROM assessment_records WHERE kind='execution_event'")
   db.commit();db.close()
  else:
   file=copied/('summary.json' if attack=='summary' else 'result.json')
   value=json.loads(file.read_text())
   if attack=='summary':value['cohorts']=[]
   elif attack=='ledger':value['ledger']['operations'][0]['elapsed_seconds']=0
   else:value['outputs_retained']=False
   file.write_text(json.dumps(value))
  try:verify(copied)
  except ValueError:results.append({'tampered':attack,'rejected':True})
  else:raise AssertionError(attack)
def strings(value):
 if isinstance(value,str):yield value
 elif isinstance(value,dict):
  for item in value.values():yield from strings(item)
 elif isinstance(value,list):
  for item in value:yield from strings(item)
observed=[]
for file in private.rglob('*.json'):observed.extend(strings(json.loads(file.read_text())))
with sqlite3.connect('file:'+str(private/'receipts.sqlite3')+'?mode=ro',uri=True) as db:
 for table in ('assessment_records','receipts','decisions'):
  for row in db.execute('SELECT payload_json FROM '+table):observed.extend(strings(json.loads(row[0])))
suite=json.loads((ROOT/'private-suite.json').read_text())
for case in suite['evals']:
 assert not any(case['prompt'] in value for value in observed)
 for text in json.loads(case['prompt'].split('\n',1)[1])['files'].values():
  assert not any(text in value for value in observed)
assert not (private/'upstream').exists()
workers=[]
for output in (retained,private):
 result=json.loads((output/'result.json').read_text())
 workers.extend(r['worker_name'] for r in result['trials'])
 assert all(r['payload_sha256']==('c91039731c19735e818c150508e6f857a218482a2371b239e4bf7b033aabbca6' if r['arm']=='treatment' else None) for r in result['trials'])
assert len(set(workers))==12
current=subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','ps','-a','--format','{{.Names}}'],text=True).splitlines()
assert not set(workers).intersection(current)
print(json.dumps({'verified_trials':12,'workers':workers,'all_task_workers_removed':True,'default_no_content_retention':True,'candidate_payload_bound':True,'negative_checks':results,'evidence_kind':'synthetic'},indent=2))
