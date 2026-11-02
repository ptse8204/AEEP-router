"""Remove this finished run's passing synthetic fixtures; keep failed cases/logs."""
import json,os,re,shutil,stat
from pathlib import Path
HERE=Path(__file__).resolve().parent
root=Path('/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/pytest-of-edwintse/pytest-1428')
assert root.resolve()==root and root.is_dir() and not root.is_symlink()
try:os.kill(56910,0)
except ProcessLookupError:pass
else:raise ValueError('Coverage process remains; preserve all resources')
log=(HERE/'verification/coverage-tests.log').read_text()
assert '42 failed, 1965 passed, 21 skipped' in log and '[100%]' in log
failed=set(re.findall(re.escape(str(root))+r"/([^/')\s]+)",log))
assert len(failed)>=25
rows=[]
for p in sorted(root.iterdir()):
 if not p.is_dir() or p.is_symlink() or p.name in failed:continue
 assert p.name.startswith('test_')
 blocks=0;files=0
 for directory,dirs,names in os.walk(p,followlinks=False):
  for name in [*dirs,*names]:
   info=(Path(directory)/name).lstat();assert info.st_uid==os.getuid()
   blocks+=info.st_blocks*512;files+=1
 rows.append({'path':str(p),'name':p.name,'allocated_bytes':blocks,'entries':files})
record={'scope':'Only passing synthetic fixtures created by this completed first-party coverage invocation; no earlier pytest roots, failed fixtures, reports, source, runtimes, Docker resources, user work or backups.',
 'root':str(root),'finished_pid':56910,'kept_failed_fixture_names':sorted(failed),'remove':rows,
 'allocated_bytes':sum(r['allocated_bytes'] for r in rows),'free_before':shutil.disk_usage(root).free}
with (HERE/'owned-fixture-cleanup.json').open('x') as f:json.dump(record,f,indent=2)
for row in rows:
 p=Path(row['path']);assert p.parent==root and p.name not in failed and p.is_dir() and not p.is_symlink()
 shutil.rmtree(p)
record['free_after']=shutil.disk_usage(root).free;record['completed']=True
(HERE/'owned-fixture-cleanup.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'removed_passing_fixture_directories':len(rows),'kept_failed_directories':len(failed),
 'allocated_bytes_removed':record['allocated_bytes'],'free_gib':record['free_after']/1024**3}))
