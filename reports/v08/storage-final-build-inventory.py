"""Bind existing final build outputs; no installation, extraction or execution of archive code."""
import hashlib,json,tarfile,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/v08/storage-attribution-inventory.json';V=ROOT/'reports/v08/delivery-boundary-validation-94f3fad31d28.json';validation=json.loads(V.read_text());phase=next(x for x in validation['checks'] if x['name']=='package-build');assert validation['complete'] and validation['source_unchanged'] and phase['exit_code']==0 and phase['source_unchanged'];assert verification_source_digest(ROOT)==validation['source_digest']
artifacts={}
for name in ('aeep_agent_router-0.8.0-py3-none-any.whl','aeep_agent_router-0.8.0.tar.gz'):
 p=ROOT/'dist'/name;before=p.stat();value={'path':str(p),'compressed_bytes':before.st_size,'allocated_artifact_bytes':before.st_blocks*512,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'modified_at':datetime.fromtimestamp(before.st_mtime,timezone.utc).isoformat()};groups=defaultdict(lambda:{'members':0,'uncompressed_bytes':0})
 if p.suffix=='.whl':
  with zipfile.ZipFile(p) as archive:
   members=[x for x in archive.infolist() if not x.is_dir()];value['uncompressed_member_bytes']=sum(x.file_size for x in members);value['members']=len(members)
   for m in members:
    group='packaged_data' if '.data/' in m.filename else 'distribution_metadata' if '.dist-info/' in m.filename else 'package_code_and_resources';groups[group]['members']+=1;groups[group]['uncompressed_bytes']+=m.file_size
   value['bytecode_members']=sum(x.filename.endswith('.pyc') for x in members);value['entry_point_metadata_present']=any(x.filename.endswith('entry_points.txt') for x in members)
 else:
  with tarfile.open(p,'r:gz') as archive:
   members=archive.getmembers();regular=[x for x in members if x.isfile()];value.update(uncompressed_regular_member_bytes=sum(x.size for x in regular),members=len(members),regular_file_members=len(regular),symlink_members=sum(x.issym() for x in members),hardlink_members=sum(x.islnk() for x in members))
 value['groups']=dict(groups);after=p.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns);value['stable_during_read']=True;artifacts[name]=value
record=json.loads(OUT.read_text());record['final_build_artifacts']={'observed_at':datetime.now(timezone.utc).isoformat(),'source_digest':validation['source_digest'],'existing_validation_record':str(V),'validation_record_sha256':hashlib.sha256(V.read_bytes()).hexdigest(),'package_build_phase':phase,'build_log_sha256':hashlib.sha256((ROOT/'reports/v08'/phase['log']).read_bytes()).hexdigest(),'artifacts':artifacts,'attribution':'AEEP-owned final wheel and source distribution archive bytes, from the completed source94 package-build phase. Not fresh-installed incremental system bytes; dependencies are excluded. Prior aeep_wheel_snapshot remains unchanged.','wheel_only_staging_assessment':'Static wheel-member inventory measures exact shipped AEEP payload without dependencies, imports, entry-point execution, or new installation. No staging installation performed: installers remap .data payload, generate entry-point wrappers/RECORD and may compile bytecode; unpacked archive sizes therefore are not installed physical bytes or total-system delta. Shared Python/Codex/dependencies remain separately attributed; APFS allocation and generated install bytes unknown.','source_unchanged':verification_source_digest(ROOT)==validation['source_digest'],'no_install_uninstall_extract_or_download':True,'no_model_container_resource_test':True}
OUT.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'source_digest':validation['source_digest'],'artifacts':artifacts}))
