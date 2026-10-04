"""Atomically apply exact inert callback definitions; no execution or allowance reset."""
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import ConformanceProbeRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = '50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7'
DB = ROOT / '.aeep/live-review-v3/aeep.sqlite3'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 import sys
 review_path=OUT/'c-callback-bundles-persistence-review.json'
 if sha(review_path)!=sys.argv[1]: raise ValueError('review changed')
 review=json.loads(review_path.read_text())
 assert review['persistence_authorized'] is True and review['execution_authorized'] is False
 assert review['runner_sha256']==sha(Path(__file__)) and verification_source_digest(ROOT)==SOURCE
 assert not DB.is_symlink() and (DB.stat().st_dev,DB.stat().st_ino)==(16777231,166293865)
 assert sha(ROOT/'.aeep/live-review-v3/aeep.json')==review['manifest_sha256']
 result_path=OUT/'c-callback-bundles-persistence-result.json'
 assert not result_path.exists()
 bundles=[]
 for name,expected in review['bundles'].items():
  p=OUT/name;assert sha(p)==expected
  b=json.loads(p.read_text());assert b['source_digest']==SOURCE
  verify_dependencies(b['request']['executable_dependencies']);bundles.append(b)
 c=sqlite3.connect(f'file:{DB}?mode=rw',uri=True)
 repo=AssessmentRepository(SimpleNamespace(_connection=c,_lock=threading.RLock()))
 inserted=[];reused=[]
 try:
  c.execute('BEGIN IMMEDIATE')
  before=c.execute('SELECT * FROM assessment_grants ORDER BY id').fetchall()
  repo.current_grant('onboarding')
  for b in bundles:
   request=ConformanceProbeRequest.model_validate(b['request']);assert content_digest(request)==b['request_digest']
   for x in b['records_to_store_and_review']:
    kind,identity,digest,value=x['kind'],x['identity'],x['digest'],x['value']
    assert content_digest(value)==digest
    old=c.execute('SELECT digest,payload_json FROM assessment_records WHERE kind=? AND id=?',(kind,identity)).fetchone()
    existing_review=c.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',(digest,)).fetchone()
    if old is not None:
     assert kind in {'boundary_probe_definition','c_callback_fixture_binding'}
     assert old[0]==digest and content_digest(json.loads(old[1]))==digest
     assert existing_review is not None and existing_review[0]==0
     reused.append([kind,digest]);continue
    assert existing_review is None
    c.execute('INSERT INTO assessment_records VALUES (?,?,?,?)',(kind,identity,digest,json.dumps(value)))
    c.execute('INSERT INTO assessment_reviews VALUES (?,?,0)',(digest,datetime.now(UTC).isoformat()))
    inserted.append([kind,digest])
   repo.authorize(request)
  assert c.execute('SELECT * FROM assessment_grants ORDER BY id').fetchall()==before
  assert verification_source_digest(ROOT)==SOURCE
  c.commit()
  result=dict(status='persisted_reviewed_inert',review_sha256=sys.argv[1],source_digest=SOURCE,inserted=inserted,reused_exact_reviewed=reused,grant_counters_unchanged=True,model_turns=0,operations_reserved=0,atomic_commit=True,execution_authorized=False)
  with result_path.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
  print(json.dumps(result))
 finally:
  if c.in_transaction:c.rollback()
  c.close()
if __name__=='__main__':main()
