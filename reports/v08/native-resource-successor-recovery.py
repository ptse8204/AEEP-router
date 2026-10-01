"""Actual native partial-write recovery footprint; one failed task, no replay."""
import asyncio,hashlib,json,sys,tempfile,time,shutil
from datetime import timedelta
from pathlib import Path
from aeep.assessment.models import content_digest
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import ActionConstraints,ActionRequest,ExecutorKind,Manifest,PolicyConfig,SideEffect,TaskScope,utc_now
from aeep.router import Router
from aeep.tasks import TaskReconciliation,reconcile
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/v08'; REVIEW=REPORTS/'native-resource-successor-review.json'; RESULT=REPORTS/'native-resource-successor-recovery-result.json'
CODEX=None
def disk(root):
    files=[p for p in root.rglob('*') if p.is_file() and not p.is_symlink()];return {'files':len(files),'logical_bytes':sum(p.stat().st_size for p in files),'allocated_bytes':sum(p.stat().st_blocks*512 for p in files)}
async def main():
    review=json.loads(REVIEW.read_text());assert review['execution_authorized'];assert verification_source_digest(ROOT)==review['source_digest'];assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==review['recovery_driver_sha256'];assert not RESULT.exists();assert not (REPORTS/'native-resource-successor-recovery-start.json').exists();binary=Path(review['binary']);started=time.perf_counter();phases=[]
    directory=tempfile.mkdtemp(prefix='aeep-resource-successor-recovery-')
    # Keep the owned fixture store on failure; successful canonical evidence is copied before cleanup.
    root=Path(directory).resolve();scratch=root/'scratch';scratch.mkdir();effect=scratch/'effect'
    boundary=NativeSandboxConfig(binary=str(binary),binary_sha256='sha256:'+hashlib.sha256(binary.read_bytes()).hexdigest(),project_root=str(root),read_roots=[str(Path(sys.prefix).resolve())],write_roots=[str(scratch)],single_process=True,python_binary=str(Path(sys.executable).resolve()),python_sha256='sha256:'+hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest())
    program='import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b"synthetic-resource-effect"); raise SystemExit(3)'
    spec=reference_spec('csv').model_copy(update={'kind':ExecutorKind.COMMAND,'side_effect':SideEffect.WRITE,'idempotent':False,'config':{'argv':[sys.executable,'-I','-c',program,str(effect)],'argv_literal':True,'stdin_json':True,'native_sandbox':boundary.model_dump(mode='json'),'timeout_seconds':1}})
    manifest=root/'aeep.json';manifest.write_text(Manifest(database=str(root/'.aeep/state.db'),executors=[spec],policies={'write':PolicyConfig(name='write',constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))}).model_dump_json())
    scope=TaskScope(scope_id='resource-recovery',project_root=str(root),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.WRITE,max_attempts=1,max_attempt_seconds=2,expires_at=utc_now()+timedelta(minutes=5))
    router=Router.from_manifest(manifest);repo=AssessmentRepository(router.store);digest=repo.put('task_scope',scope.scope_id,scope);repo.review(digest);router.bind_task_scope(scope.scope_id)
    phases.append({'phase':'reviewed_before_execution','disk':disk(root/'.aeep'),'elapsed_ms':(time.perf_counter()-started)*1000})
    (REPORTS/'native-resource-successor-recovery-start.json').write_text(json.dumps({'source_digest':review['source_digest'],'scope_digest':digest,'executor_fingerprint':executor_fingerprint(spec),'owned_root':str(root),'operation':'one native failed write; no replay','review_sha256':hashlib.sha256(REVIEW.read_bytes()).hexdigest()},indent=2)+'\n')
    outcome=await router.execute(ActionRequest(capability=spec.capability,policy='write',input={'text':'a\n1','delimiter':','},constraints=ActionConstraints(max_side_effect=SideEffect.WRITE)),approved_side_effect=SideEffect.WRITE)
    attempt=router.store.execution_attempt_for_decision(outcome.decision.decision_id);payload=router.task_outcome(outcome,approved_side_effect=SideEffect.WRITE)
    assert not outcome.ok and attempt.state.value=='INDETERMINATE' and effect.read_bytes()==b'synthetic-resource-effect' and payload.recovery_state=='required'
    evidence=hashlib.sha256(effect.read_bytes()).hexdigest();phases.append({'phase':'failed_write_before_close','disk':disk(root/'.aeep'),'elapsed_ms':(time.perf_counter()-started)*1000})
    receipt=outcome.receipts[0].receipt_id; await router.close();phases.append({'phase':'closed_unresolved','disk':disk(root/'.aeep'),'elapsed_ms':(time.perf_counter()-started)*1000})
    restarted=Router.from_manifest(manifest);repo=AssessmentRepository(restarted.store)
    try:
        existing=restarted.store.execution_attempt_for_decision(outcome.decision.decision_id);assert existing.state.value=='INDETERMINATE'
        effect.unlink()
        reconciliation=TaskReconciliation(attempt_id=existing.attempt_id,attempt_version=existing.version,scope_digest=digest,resolution='effects_reverted',evidence_digests=[digest])
        recovery_digest=repo.put('task_reconciliation',content_digest(reconciliation),reconciliation);repo.review(recovery_digest);resolved=reconcile(restarted,recovery_digest)
        assert resolved['state']=='FAILED' and resolved['allowance_reset'] is False and restarted.store.get_receipt(receipt) is not None
        phases.append({'phase':'reconciled_after_restart','disk':disk(root/'.aeep'),'elapsed_ms':(time.perf_counter()-started)*1000})
    finally:await restarted.close()
    phases.append({'phase':'reconciled_closed','disk':disk(root/'.aeep'),'elapsed_ms':(time.perf_counter()-started)*1000})
    canonical=ROOT/'.aeep'/review['evidence_directory']/'recovery';assert not canonical.exists();shutil.copytree(root/'.aeep',canonical)
    wall=(time.perf_counter()-started)*1000; retained=phases[-1]['disk']['logical_bytes'];limits=review['ceilings']
    report={'source_digest':review['source_digest'],'review_sha256':hashlib.sha256(REVIEW.read_bytes()).hexdigest(),'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope_digest':digest,'executor_fingerprint':executor_fingerprint(spec),'receipt_id':receipt,'effect_sha256':evidence,'task_attempts':1,'task_replays':0,'phases':phases,'recovery_wall_ms':wall,'recovery_retained_bytes':retained,'recovery_local_checks':{'wall_within_frozen_bound':wall<=limits['recovery_wall_ms'],'retention_within_frozen_bound':retained<=limits['recovery_retained_bytes'],'allowance_not_refunded':resolved['allowance_reset'] is False,'effect_reverted':not effect.exists()},'operator_attestation':'Locally observed synthetic effect was deleted and exact-reviewed reconciliation applied; not automated verification of arbitrary effects','model_turns':0,'source_unchanged':verification_source_digest(ROOT)==review['source_digest'],'temporary_measurement_store_removed_after_report':True,'canonical_store':str(canonical),'canonical_review_and_receipt_retained':True,'resource_gate_complete':False,'release_ready':False}
    RESULT.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));shutil.rmtree(root)
asyncio.run(main())
