"""Exact reviewed offline two-file image layer; no authentication or model calls."""
import hashlib
import json
import shutil
import subprocess
import os
import signal
import sys
import time
from pathlib import Path
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, StrictModel
from aeep.router import Router

class Result(StrictModel):
    facts: dict

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
path=OUT/'linux-lifecycle-idempotent-image-review.json'
assert len(sys.argv)==2 and hashlib.sha256(path.read_bytes()).hexdigest()==sys.argv[1]
review=json.loads(path.read_text());assert review['execution_authorized'] is True
assert verification_source_digest(ROOT)==review['source_digest']
assert not (OUT/'linux-lifecycle-idempotent-image-result.json').exists()
router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');service=AssessmentService(router,ROOT/'.aeep/live-review-v3/.aeep/assessments');repo=service.repository
request=ConformanceProbeRequest.model_validate(review['request']);bounds=review['bounds']
initial_free=shutil.disk_usage(ROOT).free;assert initial_free>=bounds['minimum_free_bytes']
repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions']);repo.authorize(request);verify_dependencies(request.executable_dependencies)
assert repo.get('linux_diagnostic_image_definition',request.mapping_digest)==review['definition']
worker=binding_from_config(ExecutorSpec.model_validate(review['definition']['base_profile']).managed_host_config().managed_worker);assert worker and worker.digest()==request.worker_digest
prefix=[worker.runtime,'--host','unix://'+worker.socket]
op='linux-lifecycle-idempotent-image:'+request.plan_id
repo.reserve(request,op,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=90),stage='reviewed_diagnostic_image_setup')
inspection_name='aeep-linux-image-'+hashlib.sha256(request.plan_id.encode()).hexdigest()[:24]
inspection_started=False
started=time.monotonic();facts={'operation_id':op,'model_turns':0,'cash_usd':0,'source_digest':review['source_digest'],'base_image':worker.image,'setup_complete':False};stage='base_image_inspection'
def command(argv,timeout):
    repo.authorize(request)
    remaining=bounds['setup_seconds']-(time.monotonic()-started)-13
    if remaining<=0:raise TimeoutError('overall_setup_bound')
    process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        stdout,stderr=process.communicate(timeout=min(timeout,remaining))
    except subprocess.TimeoutExpired:
        facts.setdefault('owned_process_cleanup',[]).append({'pid':process.pid,'stage':stage,'timed_out':True})
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.communicate(timeout=2)
        facts['owned_process_cleanup'][-1]['reaped']=process.returncode is not None
        facts['build_daemon_cancellation_not_independently_observed']=stage=='offline_build'
        raise
    result=subprocess.CompletedProcess(argv,process.returncode,stdout,stderr)
    stderr_text=result.stderr.decode('utf-8',errors='replace').lower()
    classes=(('metadata_resolution_failed',('failed to resolve source metadata','failed to resolve reference')),('registry_access_denied',('pull access denied','insufficient_scope','failed to authorize')),('buildkit_required',('requires buildkit','--chmod option requires')),('unsupported_flag',('unknown flag','unknown option','unexpected argument')),('dockerfile_parse_failed',('dockerfile parse error','unknown instruction')),('copy_source_missing',('failed to calculate checksum','not found in build context')))
    safe_class=next((name for name,markers in classes if any(marker in stderr_text for marker in markers)), 'unclassified' if result.stderr else 'none') if result.returncode else 'none'
    steps=[name for name,marker in [('load_definition','load build definition'),('load_metadata','load metadata'),('load_context','load build context'),('copy_requirements','copy --chmod=0444 requirements.toml'),('copy_server','copy --chmod=0444 linux-mcp-server.py'),('export_image','exporting to image')] if marker in stderr_text]
    facts.setdefault('commands',[]).append({'argv':argv,'exit_code':result.returncode,'stdout_bytes':len(result.stdout),'stderr_bytes':len(result.stderr),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest(),'stderr_class':safe_class,'known_build_steps':steps})
    if result.returncode:raise RuntimeError('owned_setup_command_failed')
    return result.stdout
try:
    base=json.loads(command(prefix+['image','inspect',review['definition']['base_reference']],5))[0];assert base['Id']==worker.image
    stage='offline_build';iid=OUT/'linux-lifecycle-idempotent-image-id';assert not iid.exists()
    command(prefix+['build','--network=none','--pull=false','--platform',worker.platform,'--progress=plain','--iidfile',str(iid.resolve()),str((OUT/'immutable-lifecycle-idempotent').resolve())],bounds['build_seconds'])
    image=iid.read_text().strip();assert image.startswith('sha256:') and len(image)==71;facts['image']=image
    assert initial_free-shutil.disk_usage(ROOT).free<=bounds['host_disk_growth_bytes']
    stage='image_inheritance_inspection'
    post_started=time.monotonic()
    pair=json.loads(command(prefix+['image','inspect',review['definition']['base_reference'],image],5))
    assert pair[0]['Id']==worker.image
    assert pair[1]['RootFS']['Layers'][:len(base['RootFS']['Layers'])]==base['RootFS']['Layers']
    assert pair[1]['Config']==base['Config']
    facts['base_layer_prefix_matches']=True;facts['inherited_runtime_config_matches']=True
    stage='no_auth_public_file_inspection' 
    paths=['/opt/codex/codex','/opt/aeep/worker-config.json','/opt/aeep/worker-launch','/etc/codex/requirements.toml','/opt/aeep/linux-mcp-server.py']
    program='import hashlib,json,pathlib;paths='+repr(paths)+';r={};\nfor p in paths:\n with pathlib.Path(p).open("rb") as f:r[p]=hashlib.file_digest(f,"sha256").hexdigest()\nprint(json.dumps(r))'
    inspection_started=True
    facts['inspection_container_name']=inspection_name
    observed=json.loads(command(prefix+['run','--name',inspection_name,'--rm','--network=none','--read-only','--user','65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges','--entrypoint','/usr/local/bin/python3',image,'-c',program],max(0.001,bounds['inspection_seconds']-(time.monotonic()-post_started))))
    assert observed['/opt/codex/codex']==worker.binary_sha256
    assert observed['/opt/aeep/worker-config.json']==worker.configuration_digest
    assert observed['/etc/codex/requirements.toml']==review['definition']['files'][str((OUT/'immutable-lifecycle-idempotent/requirements.toml').resolve())]
    assert observed['/opt/aeep/linux-mcp-server.py']==review['definition']['files'][str((OUT/'immutable-lifecycle-idempotent/linux-mcp-server.py').resolve())]
    facts['public_file_sha256']=observed;facts['setup_complete']=True
except Exception as exc:
    facts['error_type']=type(exc).__name__;facts['failed_stage']=stage
finally:
    if inspection_started:
        cleanup_started=time.monotonic()
        try:
            def owned_ids():
                result=subprocess.run(prefix+['ps','--all','--quiet','--filter','name=^/'+inspection_name+'$'],capture_output=True,timeout=2,env={})
                if result.returncode:raise RuntimeError('owned_container_inspection_failed')
                return result.stdout.strip()
            if owned_ids():
                removed=subprocess.run(prefix+['rm','--force',inspection_name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3,env={})
                if removed.returncode:raise RuntimeError('owned_container_remove_failed')
            facts['inspection_cleanup_confirmed']=not bool(owned_ids())
        except Exception as exc:
            facts['inspection_cleanup_confirmed']=False
            facts['inspection_cleanup_error_type']=type(exc).__name__
        facts['inspection_cleanup_seconds']=time.monotonic()-cleanup_started
        if not facts['inspection_cleanup_confirmed']:facts['setup_complete']=False
    facts['elapsed_seconds']=time.monotonic()-started;facts['host_free_delta_bytes']=initial_free-shutil.disk_usage(ROOT).free;facts['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];repo.finish_operation(op,elapsed_seconds=facts['elapsed_seconds'],accounting=None,resources=None)
    document=Result(facts=facts);facts['canonical_record_digest']=repo.put('linux_diagnostic_image_observation',content_digest(document),document)
    (OUT/'linux-lifecycle-idempotent-image-result.json').write_text(json.dumps(facts,indent=2)+'\n');print(json.dumps(facts));router.store.close()
