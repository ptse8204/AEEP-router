"""Source-bound native backend renewal; exact existing checks only."""
import asyncio, hashlib, json, os, subprocess, time
from pathlib import Path
from aeep.assessment.models import AssessmentPlanningRequest, AssessmentLimits
from aeep.assessment.repository import AssessmentRepository
from aeep.models import StrictModel
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'
BINARY='/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
class Definition(StrictModel):
    argv: list[str]
    binary_sha256: str
    maximum_seconds: int=180
    model_turns: int=0
async def main():
    r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json'); repo=AssessmentRepository(r.store)
    old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    argv=['python3','-m','pytest','-q','tests/test_v08_task_profile.py::test_actual_native_allow_deny_and_network_boundary','tests/test_v08_task_lifecycle.py::test_actual_codex_project_mcp_discovery_call_pause_and_uninstall']
    definition=Definition(argv=argv,binary_sha256=hashlib.sha256(Path(BINARY).read_bytes()).hexdigest())
    mapping=repo.put('native_host_diagnostic','sol61-desktop-boundaries-288e',definition); repo.review(mapping)
    req=old.model_copy(update={'plan_id':'planning_native_desktop_boundaries_288e','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]})
    digest=repo.put('planning_request',req.plan_id,req); repo.review(digest); repo.authorize(req)
    review={'authority':'standing September25/27 exact review delegation','definition':definition.model_dump(),'mapping_digest':mapping,'request_digest':digest,'classification':'existing native boundary and direct MCP lifecycle renewal for0.159.2; no model, planner, worker conformance or qualification','driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (REPORTS/'native-sol61-desktop-boundaries-review-288e.json').write_text(json.dumps(review,indent=2))
    op='native-boundaries:'+req.plan_id; repo.reserve(req,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=180),stage='native_host_boundary_renewal')
    began=time.perf_counter(); env=dict(os.environ,AEEP_NATIVE_CODEX=BINARY)
    try:
        result=await asyncio.to_thread(subprocess.run,argv,cwd=ROOT,env=env,capture_output=True,text=True,timeout=170)
        (REPORTS/'native-sol61-desktop-boundaries-288e.log').write_text(result.stdout+result.stderr)
        record={'exit_code':result.returncode,'stdout_bytes':len(result.stdout.encode()),'stderr_bytes':len(result.stderr.encode()),'model_turns':0}
    except BaseException as exc: record={'error_type':type(exc).__name__}
    elapsed=time.perf_counter()-began; repo.finish_operation(op,elapsed_seconds=elapsed)
    record.update(operation_id=op,elapsed_seconds=elapsed,grant_after=list(r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(req.authorization_id,)).fetchone()))
    (REPORTS/'native-sol61-desktop-boundaries-result-288e.json').write_text(json.dumps(record,indent=2));print(json.dumps(record));await r.close()
asyncio.run(main())
