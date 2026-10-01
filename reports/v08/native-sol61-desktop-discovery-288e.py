"""Exact-reviewed, charged native catalog introspection; no planner or model execution."""
import asyncio, hashlib, json, tempfile, time
from pathlib import Path
from datetime import datetime, timezone
from aeep.assessment.models import AssessmentPlanningRequest, AssessmentLimits, ConformanceProbeRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerTransport
from aeep.models import StrictModel
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[2]
REPORTS=ROOT/'reports/v08'
SOURCE='288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
WRAPPER=BINARY.parents[3]/'bin/codex'
class Diagnostic(StrictModel):
    executable: str
    binary_sha256: str
    version: str
    wrapper: str
    wrapper_sha256: str
    method: str='model/list includeHidden=true'
    maximum_seconds: int=35
    maximum_turns: int=0
    classification: str='native introspection; authorization planning envelope only; no planner execution or worker conformance'
async def main():
    assert verification_source_digest(ROOT)==SOURCE
    result_path=REPORTS/'native-sol61-desktop-discovery-result-288e.json'
    assert not result_path.exists()
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json')
    repo=AssessmentRepository(router.store)
    old=ConformanceProbeRequest.model_validate(repo.get('conformance_request','conformance_probe_a1b5f5d158f5490abed097078a10c8d7'))
    definition=BoundaryProbeDefinition.model_validate(repo.get('boundary_probe_definition',old.mapping_digest))
    diagnostic=Diagnostic(executable=str(BINARY),binary_sha256='sha256:'+hashlib.sha256(BINARY.read_bytes()).hexdigest(),version='0.159.2',wrapper=str(WRAPPER),wrapper_sha256=hashlib.sha256(WRAPPER.read_bytes()).hexdigest())
    mapping=repo.put('native_host_diagnostic','sol61-desktop-model-discovery-288e',diagnostic); repo.review(mapping)
    request=AssessmentPlanningRequest(subject_digest=old.subject_digest,recipe_digest=old.recipe_digest,mapping_digest=mapping,environment_digest=old.environment_digest,authorization_id=old.authorization_id,definition_digests=[*old.definition_digests,mapping],planner=definition.executor)
    request_digest=repo.put('planning_request',request.plan_id,request); repo.review(request_digest); repo.authorize(request)
    grant_before=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
    review={'recorded_at':datetime.now(timezone.utc).isoformat(),'authority':'September 25/27 standing exact review delegation; September 30 unfinished tests model selection','source_digest':SOURCE,'diagnostic':diagnostic.model_dump(),'mapping_digest':mapping,'request_id':request.plan_id,'request_digest':request_digest,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'maximum_operations':1,'maximum_seconds':35,'maximum_model_turns':0,'maximum_cash_usd':0,'grant_before':grant_before,'auth_access':False,'global_config_changes':False,'historical_evidence_transfer':False}
    with (REPORTS/'native-sol61-desktop-discovery-review-288e.json').open('x') as f: json.dump(review,f,indent=2)
    operation='native-desktop-discovery:'+request.plan_id
    repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=35),stage='native_host_model_discovery')
    began=time.perf_counter(); observations={'models':[],'complete':False,'cleanup_confirmed':False,'model_turns':0}; transport=None
    try:
        with tempfile.TemporaryDirectory(prefix='aeep-desktop-model-discovery-') as directory:
            transport=CodexAppServerTransport((str(BINARY),'app-server','-c','mcp_servers={}','-c','features.apps=false'),environment_allowlist=('HOME','CODEX_HOME','PATH'),cwd=str(Path(directory).resolve()),executable_sha256=diagnostic.binary_sha256,request_timeout=15)
            try:
                async with asyncio.timeout(30):
                    cursor=None; seen=set()
                    for _ in range(100):
                        params={'includeHidden':True}
                        if cursor: params['cursor']=cursor
                        value=await transport.request('model/list',params,timeout=15)
                        assert isinstance(value.get('data'),list)
                        for item in value['data']:
                            observations['models'].append({'id':item.get('model') or item.get('id'),'reasoning_efforts':[e['reasoningEffort'] for e in item.get('supportedReasoningEfforts',[])]})
                        cursor=value.get('nextCursor')
                        if not cursor: observations['complete']=True; break
                        assert cursor not in seen; seen.add(cursor)
            finally:
                await asyncio.wait_for(transport.close(),5); observations['cleanup_confirmed']=not transport.running
    except BaseException as exc: observations['error_type']=type(exc).__name__
    finally:
        elapsed=time.perf_counter()-began; repo.finish_operation(operation,elapsed_seconds=elapsed)
        grant_after=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
        output={'source_digest':SOURCE,'operation_id':operation,'diagnostic_digest':mapping,'observations':observations,'elapsed_seconds':elapsed,'grant_after':grant_after,'reviewed_model_present':any(x['id']=='gpt-6.1-sol' for x in observations['models']),'source_unchanged':verification_source_digest(ROOT)==SOURCE,'release_ready':False,'replay_allowed':False}
        with result_path.open('x') as f: json.dump(output,f,indent=2)
        print(json.dumps(output)); await router.close()
asyncio.run(main())
