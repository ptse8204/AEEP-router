"""Replay frozen historical observer replies through full current grader validation.

No repository code, container or model is executed. Historical replies remain
historical; this checks definition wiring and cannot establish current conformance.
"""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.assessment import extensions
from aeep.assessment.models import RecipeDefinition,content_digest
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    prior=HERE.parent/'repository-model-journey-20261022';proposal=json.loads((HERE/'collector-definitions.json').read_text());boundary=json.loads((HERE/'boundary-result.json').read_text())
    paths=[HERE.parent/'repository-suite-integration-20261022/grader-execution-result.json',HERE.parent/'repository-suite-continuation-20261022/execution-result.json',HERE.parent/'repository-suite-semantic-fault-20261022/raw-observation.json']
    lookup={}
    for path in paths:
        data=json.loads(path.read_text());rows=data.get('results',[data])
        for row in rows:
            reply=row.get('observations',row.get('output'))
            if isinstance(reply,dict) and set(reply)=={'statuses','exit_code','archive_sha256','python','pytest'}:lookup[reply['archive_sha256']]=reply
    spec=importlib.util.spec_from_file_location('corrected_replay_plan',HERE/'run-corrected.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    _,recipe,_,_,plan,_=module.load_runner().construct(proposal,boundary)
    original=extensions.invoke;calls=[]
    async def invoke(service,scope,executor,value,**kwargs):
        reply=lookup.get(value['archive_sha256'])
        if reply is None:raise LookupError('No retained historical reply; do not invent an observation')
        assert value['python']==reply['python'] and value['pytest']==reply['pytest']
        calls.append({'archive_sha256':value['archive_sha256'],'historical_reply_sha256':content_digest(reply)})
        return reply,0.0
    extensions.invoke=invoke
    try:literals,faults=await extensions.validate_grader(None,plan,recipe,[])
    finally:extensions.invoke=original
    assert len(literals)==3 and len(calls)==15 and faults==48
    review=json.loads((HERE/'operation-review.json').read_text())
    assert all(sha(Path(path))==digest for path,digest in review['assets'].items())
    result={'passed':True,'kind':'historical_observer_reply_replay_fixture','source_digest':verification_source_digest(ROOT),'recipe_digest':content_digest(recipe),'historical_inputs':{str(p.relative_to(ROOT)):sha(p) for p in paths},'literal_fixtures':len(literals),'replayed_physical_calls':len(calls),'faults_rejected':faults,'total_validation_decisions':57,'unique_historical_archives':len({c['archive_sha256'] for c in calls}),'calls':calls,'actual_worker_or_model_executions':0,'actual_grant_operations_added':0,'current_runtime_conformance':False,'qualification_or_usefulness_or_selection_claim':False,'exact_pending_review_assets_unchanged':True}
    (HERE/'grader-replay-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['calls','historical_inputs']}))


if __name__=='__main__':asyncio.run(main())
