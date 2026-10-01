import hashlib,json,shutil,subprocess,time
from pathlib import Path
from aeep.router import Router
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.models import ConformanceProbeRequest,AssessmentLimits
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4'
assert verification_source_digest(ROOT)==SOURCE
assert not(OUT/'build-correction-result.json').exists()
review=json.loads((OUT/'build-correction-review.json').read_text());context=OUT/'context'
assert hashlib.sha256((context/'Dockerfile').read_bytes()).hexdigest()==review['context_dockerfile_sha256']
assert hashlib.sha256((OUT/'official-package.tar.gz').read_bytes()).hexdigest()==review['archive_sha256']
for name,digest in review['runtime_sha256'].items():assert hashlib.sha256((context/'runtime'/name).read_bytes()).hexdigest()==digest
for arm,ref in review['refs'].items():assert subprocess.check_output(['docker','image','inspect','--format','{{.Id}} {{.Config.User}}',ref],text=True).strip()==ref.split('@')[1]+' 65534:65534'
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(r.store);request=ConformanceProbeRequest.model_validate(review['request']);op=request.plan_id+':build_correction';repo.reserve(request,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=400),stage='reviewed_successor_build_correction')
began=time.monotonic();initial_free=shutil.disk_usage(ROOT).free;result={'operation_id':op,'source_digest':SOURCE,'images':{},'new_download_bytes':0,'model_turns':0,'auth_access':False};stage='preflight'
try:
 for arm in ['control','treatment']:
  repo.authorize(request);stage='build_'+arm;tag='aeep-sol61-successor-'+arm+':1592'
  if subprocess.run(['docker','image','inspect',tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0:raise RuntimeError('successor tag already exists; preserve')
  iid=OUT/(arm+'-image-id');cmd=['docker','build','--network=none','--pull=false','--platform','linux/arm64','--progress=plain','--target',arm,'--tag',tag,'--iidfile',str(iid.resolve()),str(context.resolve())]
  with(OUT/(arm+'-build-corrected.log')).open('wb') as log:res=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  if res.returncode:raise RuntimeError('offline build failed')
  result['images'][arm]=iid.read_text().strip()
  if initial_free-shutil.disk_usage(ROOT).free>3000000000:raise RuntimeError('disk growth cap')
 result['setup_complete']=True
except BaseException as exc:result.update(setup_complete=False,failed_stage=stage,error_type=type(exc).__name__,error_summary=str(exc)[:160])
finally:
 elapsed=time.monotonic()-began;repo.finish_operation(op,elapsed_seconds=elapsed);result.update(elapsed_seconds=elapsed,host_free_bytes_before=initial_free,host_free_bytes_after=shutil.disk_usage(ROOT).free,source_unchanged=verification_source_digest(ROOT)==SOURCE,replay_allowed=False)
 row=r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone();result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row));(OUT/'build-correction-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));r.store.close()
