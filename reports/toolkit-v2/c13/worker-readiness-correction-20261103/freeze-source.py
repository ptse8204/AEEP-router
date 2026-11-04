"""Retain exact source bytes locally, including preserved unrelated CI edits."""
import shutil
from pathlib import Path
import integration as prepared
from aeep.assessment.verification import verification_source_digest
ROOT=prepared.ROOT;HERE=prepared.HERE
assert shutil.disk_usage(ROOT).free>=50*1024**3+32*1024**2
source=verification_source_digest(ROOT)
frozen=ROOT/('.aeep/stack-frozen-source-'+source[:12])
frozen.mkdir(mode=0o700,exist_ok=True)
paths=[ROOT/'pyproject.toml']
for name in ('src','tests','integrations/aeep','integrations/assessment-runtime','integrations/managed-worker','scripts'):
 paths.extend((ROOT/name).rglob('*'))
files={}
for path in sorted(paths):
 if not path.is_file() or any(part=='__pycache__' or part.endswith('.egg-info') for part in path.parts):continue
 assert not path.is_symlink()
 relative=path.relative_to(ROOT);target=frozen/relative
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():assert prepared.sha(target)==prepared.sha(path)
 else:shutil.copyfile(path,target)
 files[str(relative)]=prepared.sha(path)
assert verification_source_digest(frozen)==source
prepared.write(HERE/'source-snapshot.json',{'source':source,'path':str(frozen),'files':files,
 'scope':'Exact tested checkout. Includes unrelated pyproject/tests CI edits preserved locally and excluded from this feature commit. No source was changed or executed by this copy.',
 'snapshot_is_not_a_new_execution_permission':True})
print({'source':source,'files':len(files),'copied_bytes':sum((frozen/name).stat().st_size for name in files)})
