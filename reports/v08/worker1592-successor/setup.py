"""Bounded reviewed lab-only successor setup; no authentication or model calls."""
import hashlib,json,os,shutil,subprocess,tarfile,time,urllib.request
from pathlib import Path,PurePosixPath
from aeep.router import Router
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.models import AssessmentLimits,ConformanceProbeRequest
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4'
review=json.loads((OUT/'setup-review.json').read_text())
assert hashlib.sha256((OUT/'setup-review.json').read_bytes()).hexdigest()=='61e60eb61e507554b119bed751306547f5c6732dcb11b227fe52a08737dacca4'
assert verification_source_digest(ROOT)==SOURCE
assert not (OUT/'setup-result.json').exists()
bounds=review['bounds'];assert shutil.disk_usage(ROOT).free>=bounds['minimum_host_free_bytes']
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(r.store);request=ConformanceProbeRequest.model_validate(review['request']);repo.authorize(request)
op=request.plan_id+':successor_setup';repo.reserve(request,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=bounds['total_setup_seconds']),stage='reviewed_successor_setup')
began=time.monotonic();cpu_began=time.process_time();initial_free=shutil.disk_usage(ROOT).free;result={'source_digest':SOURCE,'operation_id':op,'model_turns':0,'cash':0,'images':{},'auth_access':False,'old_images_preserved':True};stage='download'
def check():
 repo.authorize(request)
 if time.monotonic()-began>bounds['total_setup_seconds']:raise TimeoutError('setup cap')
 if initial_free-shutil.disk_usage(ROOT).free>bounds['lab_disk_growth_bytes']:raise RuntimeError('disk growth cap')
try:
 archive=OUT/'official-package.tar.gz';h=hashlib.sha256();size=0;start=time.monotonic()
 with urllib.request.urlopen(review['artifact']['browser_download_url'],timeout=30) as response,archive.open('xb') as target:
  while chunk:=response.read(1024*1024):
   size+=len(chunk)
   if size>bounds['download_bytes'] or time.monotonic()-start>bounds['download_seconds']:raise RuntimeError('download cap')
   target.write(chunk);h.update(chunk);check()
 if 'sha256:'+h.hexdigest()!=review['artifact']['digest'] or size!=review['artifact']['size']:raise ValueError('official artifact digest/size mismatch')
 result['download_bytes']=size;result['archive_sha256']=h.hexdigest();stage='archive_inspection'
 extract=OUT/'package';extract.mkdir()
 with tarfile.open(archive,'r:gz') as tar:
  members=tar.getmembers()
  if len(members)>bounds['member_count'] or sum(m.size for m in members)>bounds['unpacked_bytes']:raise ValueError('archive limits')
  result['unpacked_declared_bytes']=sum(m.size for m in members)
  inventory=[]
  for m in members:
   path=PurePosixPath(m.name)
   if path.is_absolute() or '..' in path.parts or not(m.isfile() or m.isdir() or m.issym()):raise ValueError('unsafe archive member')
   if m.issym():
    link=PurePosixPath(m.linkname)
    if link.is_absolute() or '..' in link.parts:raise ValueError('external symlink')
   inventory.append({'name':m.name,'bytes':m.size,'kind':'file' if m.isfile() else 'directory' if m.isdir() else 'symlink'})
  (OUT/'package-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
  tar.extractall(extract,filter='data')
 check();stage='runtime_context'
 context=OUT/'context';runtime=context/'runtime';runtime.mkdir(parents=True)
 allfiles=list(extract.rglob('*'));required={}
 for name in ['codex','codex-code-mode-host','rg']:
  candidates=[p for p in allfiles if p.name==name and p.is_file() and not p.is_symlink()]
  if len(candidates)!=1:raise ValueError('required runtime member missing/ambiguous: '+name)
  shutil.copy2(candidates[0],runtime/name);required[name]=hashlib.sha256((runtime/name).read_bytes()).hexdigest()
 resources=[p for p in allfiles if p.name=='codex-resources' and p.is_dir()]
 if len(resources)!=1:raise ValueError('codex-resources missing/ambiguous')
 shutil.copytree(resources[0],runtime/'codex-resources',symlinks=True)
 shutil.copy2(OUT/'LICENSE',context/'LICENSE')
 notices=[]
 for member in allfiles:
  if member.is_file() and not member.is_symlink() and member.name.upper().startswith(('LICENSE','NOTICE','COPYING')):
   relative=member.relative_to(extract);destination=runtime/'notices'/relative
   destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(member,destination)
   notices.append({'path':str(relative),'sha256':hashlib.sha256(member.read_bytes()).hexdigest()})
 result['package_notices']=notices
 result['runtime_sha256']=required
 lines=[]
 for arm,base in review['base_images'].items():
  lines += [f'FROM {base} AS {arm}','USER root','RUN ["rm", "-rf", "/opt/codex"]','COPY runtime/ /opt/codex/','COPY LICENSE /opt/codex/LICENSE','USER 65534:65534']
 (context/'Dockerfile').write_text('\n'.join(lines)+'\n')
 result['context_bytes']=sum(p.stat().st_size for p in context.rglob('*') if p.is_file())
 for arm in ['control','treatment']:
  tag='aeep-sol61-successor-'+arm+':1592'
  if subprocess.run(['docker','image','inspect',tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0:raise RuntimeError('successor tag already exists; preserve it')
  check();stage='build_'+arm;iid=OUT/(arm+'-image-id');cmd=['docker','build','--network=none','--pull=false','--platform','linux/arm64','--progress=plain','--target',arm,'--tag','aeep-sol61-successor-'+arm+':1592','--iidfile',str(iid.resolve()),str(context.resolve())]
  with (OUT/(arm+'-build.log')).open('wb') as log:completed=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=bounds['build_seconds_per_arm'])
  if completed.returncode:raise RuntimeError('offline build failed')
  result['images'][arm]=iid.read_text().strip();check()
 result['setup_complete']=True
except BaseException as exc:
 result.update(setup_complete=False,failed_stage=stage,error_type=type(exc).__name__,error_summary=str(exc)[:160])
finally:
 elapsed=time.monotonic()-began;repo.finish_operation(op,elapsed_seconds=elapsed)
 result.update(coordinator_cpu_ms=(time.process_time()-cpu_began)*1000,host_free_bytes_before=initial_free,host_free_bytes_after=shutil.disk_usage(ROOT).free,resource_limitations='Coordinator CPU excludes network daemon and build workers; host free delta may include other activity. No inferred whole-worker savings.',elapsed_seconds=elapsed,source_unchanged=verification_source_digest(ROOT)==SOURCE,replay_allowed=False)
 row=r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone();result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row))
 (OUT/'setup-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));r.store.close()
