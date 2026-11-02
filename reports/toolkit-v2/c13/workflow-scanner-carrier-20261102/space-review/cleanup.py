"""Delete only reviewed obsolete test snapshots after exact operator approval."""
import argparse,hashlib,json,os,re,shutil,sqlite3,stat,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
TARGET=Path('/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/pytest-of-edwintse/pytest-1345/test_complete_assessment_admis0/assessment/plan_548e72c536264761a3827bbe091058c5/attempts')
FIXTURE=TARGET.parents[2]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory():
 assert TARGET.resolve()==TARGET and not TARGET.is_symlink() and TARGET.is_dir()
 assert (FIXTURE/'plugin.txt').read_text()=='a reviewed local fixture'
 try:os.kill(6134,0)
 except ProcessLookupError:pass
 else:raise ValueError('Original pytest PID exists; preserve all resources')
 opened=subprocess.run(['/usr/sbin/lsof','-t','+D',str(TARGET)],capture_output=True,text=True,timeout=30)
 assert opened.returncode==1 and not opened.stdout and not opened.stderr,'Open/unknown handles; preserve snapshots'
 rows=[]
 allowed={'aeep.assessment.recipes:reference_csv','test_v08_assessment:slow_csv'}
 for path in sorted(TARGET.iterdir()):
  info=path.lstat()
  assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
  assert re.fullmatch(r'worker_[a-f0-9]{32}\.sqlite3',path.name)
  with sqlite3.connect('file:'+str(path)+'?mode=ro&immutable=1',uri=True) as db:
   mappings=db.execute("SELECT payload_json FROM assessment_records WHERE kind='mapping'").fetchall()
   assert mappings
   for raw, in mappings:
    value=json.loads(raw)
    for spec in (value['candidate'],value['baseline'],*value.get('dependencies',[])):
     assert spec['kind']=='python' and spec['config']['callable'] in allowed
   environments=db.execute("SELECT payload_json FROM assessment_records WHERE kind='environment'").fetchall()
   assert environments and all(json.loads(raw)['environment_id']=='local' for raw, in environments)
  rows.append({'name':path.name,'sha256':sha(path),'bytes':info.st_size,'allocated_bytes':info.st_blocks*512,'inode':info.st_ino,'mtime_ns':info.st_mtime_ns})
 assert len(rows)==283
 preserved={str(path):sha(path) for path in [FIXTURE/'plugin.txt',*sorted((FIXTURE/'assessment').glob('*/campaign.sqlite3'))]}
 assert len(preserved)==3
 return {'target':str(TARGET),'directory_inode':TARGET.stat().st_ino,'uid':os.getuid(),'files':rows,'preserved_primary_files':preserved}

def main():
 p=argparse.ArgumentParser();p.add_argument('--execute-approved');args=p.parse_args()
 review=json.loads((HERE/'operation-review.json').read_bytes());identity=sha(HERE/'operation-review.json')
 assert sha(Path(__file__))==review['driver_sha256']
 assert inventory()==review['inventory']
 if args.execute_approved is None:
  print(json.dumps({'review_sha256':identity,'executed':False,'files':283}));return
 assert args.execute_approved==identity
 approval=json.loads((HERE/'operator-approval.json').read_bytes());assert approval['approved'] and approval['review_sha256']==identity
 with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity},f)
 before=shutil.disk_usage(TARGET).free;start=time.monotonic()
 # Every file, ownership, inode and primary evidence file was rechecked above.
 shutil.rmtree(TARGET)
 assert not TARGET.exists()
 for name,value in review['inventory']['preserved_primary_files'].items():assert sha(Path(name))==value
 after=shutil.disk_usage(HERE).free
 result={'passed':True,'review_sha256':identity,'files_removed':283,'free_before':before,'free_after':after,'actual_free_bytes_recovered':after-before,
  'allocated_bytes_removed':sum(row['allocated_bytes'] for row in review['inventory']['files']),
  'primary_campaign_files_preserved':True,'docker_touched':False,'models':0,'seconds':time.monotonic()-start}
 (HERE/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
