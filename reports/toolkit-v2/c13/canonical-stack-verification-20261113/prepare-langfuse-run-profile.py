"""Prepare narrow native boundaries for the current-source telemetry CLI."""

from pathlib import Path
import hashlib,json,os,sys
from aeep.assessment.models import AssessmentRunBinding
from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore

root=Path.cwd().resolve()
state=Path(sys.argv[1]).resolve()
owned=Path(sys.argv[2]).resolve()
owned.mkdir(mode=0o700)
for name in ('home','tmp'):(owned/name).mkdir(mode=0o700)
data=json.loads(state.read_bytes())
db=Path(data['database'])
directories={root/'src',root/'tests',root/'scripts',root/'integrations/aeep',
             root/'integrations/assessment-runtime',root/'integrations/managed-worker',
             owned,Path(data['manifest']['path']).parent,Path(sys.executable).resolve().parents[1]}
# The private package runtime is the previous public dependency carrier;
# current source is loaded explicitly before those installed dependencies.
package=Path('/Users/edwintse/Documents/aeep-toolkit-v2/.aeep/workflow-telemetry-20261104/package/installed-runtime')
site=next((package/'lib').glob('python*/site-packages'))
directories.add(site)
files={root/'pyproject.toml'}
def sqlite_files(path):
    return {path,*[Path(str(path)+suffix) for suffix in ('-wal','-shm','-journal')]}
files |= sqlite_files(db)
with ReceiptStore(db,read_only=True) as live:
 repo=AssessmentRepository(live)
 for domain,cfg in data['configurations'].items():
  for variant in cfg['variants']:
   workflow=json.loads(Path(variant['workflow']['path']).read_text())
   plan_file=Path(workflow['configurations'][domain]['assessment']['plan']['path'])
   plan=json.loads(plan_file.read_text())
   files.add(plan_file)
   binding=AssessmentRunBinding.model_validate(repo.get('run_binding',plan['plan_id']))
   campaign=Path(binding.campaign_path)
   files |= sqlite_files(campaign)
   with ReceiptStore(campaign,read_only=True) as s:
    match=s._connection.execute('SELECT trial_id FROM trial_receipts WHERE receipt_id=?',(cfg['receipt_id'],)).fetchone()
    attempt,=s._connection.execute('SELECT database_path FROM trial_stores WHERE trial_id=?',match).fetchone()
    files |= sqlite_files(Path(attempt))
def expression(qualifier, paths):
 return ' '.join('('+qualifier+' '+json.dumps(str(path))+')' for path in sorted(paths))
metadata={ancestor for x in {*files,*directories} for ancestor in [x,*x.parents] if str(ancestor).startswith('/Users')}
policy=['(version 1)','(allow default)','(deny network*)','(deny file-write*)',
        '(allow file-write* (literal "/dev/null") '+expression('literal',sqlite_files(db))+' '+expression('subpath',[owned/'tmp',owned/'home'])+')',
        '(deny file-read* (subpath "/Users"))',
        '(allow file-read* '+expression('subpath',directories)+' '+expression('literal',files)+')',
        '(allow file-read-metadata '+expression('literal',metadata)+')']
for name,rest in [('disabled',[]),('enabled',['(allow network-outbound (remote ip "localhost:39067"))'])]:
 (owned/(name+'.sb')).write_text('\n'.join(policy+rest)+'\n')
entry=owned/'entry.py'
entry.write_text('import sys\n'+f'sys.path[:0] = [{str(root/"src")!r}, {str(site)!r}]\n'
                 +'from aeep_toolkit.cli import main\nraise SystemExit(main(sys.argv[1:]))\n')
print(json.dumps({'entry':str(entry),'checked_campaigns':len(data['configurations']),
                  'eligible_network_destination':'127.0.0.1:39067','network_credentials':'task-owned local Langfuse only',
                  'profiles':{name:hashlib.sha256((owned/(name+'.sb')).read_bytes()).hexdigest() for name in ('enabled','disabled')},
                  'receipt_store_writes':'existing managed ledger only, no writes to campaign or attempt stores'},indent=2))
