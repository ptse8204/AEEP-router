"""First-party driver substitutions only; no Docker, upstream image or network."""
import asyncio
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import RawExecution,StrictModel
from aeep.store import ReceiptStore

loader=importlib.util.spec_from_file_location('bounded_artifact_acquisition',HERE/'run-acquisition.py')
module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
prepared=json.loads((HERE/'acquisition-preparation.json').read_bytes())
images=json.loads((HERE/'image-acquisition-plan.json').read_bytes())['images']


def scenario(kind):
    with tempfile.TemporaryDirectory(prefix='aeep-acquisition-first-party-') as temporary:
        folder=Path(temporary);local=dict(prepared,ledger=str(folder/'fixture.sqlite3'))
        (folder/'acquisition-preparation.json').write_text(json.dumps(local))
        module.HERE=folder;module.ROOT=folder;module.validate=lambda _:None
        request=RecipeMaterializationRequest.model_validate(local['request'])
        grant=AssessmentAuthorization.model_validate(local['grant'])
        old=grant.model_copy(update={'authorization_id':'unrelated-fixture-grant'})
        with ReceiptStore(local['ledger']) as store:
            repo=AssessmentRepository(store)
            repo.grant(old)
            store._connection.execute('UPDATE assessment_grants SET operations=7,elapsed_seconds=1.25 WHERE id=?',(old.authorization_id,))
            store._connection.commit()
            before=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(old.authorization_id,)).fetchone())
        calls=[]

        async def substitute(repo,request,review,operation,arguments,seconds):
            clock=time.perf_counter()
            repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=seconds+10),stage='explicit_first_party_substitution')
            calls.append(arguments)
            target=arguments[-1] if arguments[:2]==['image','pull'] else arguments[2]
            first=target==images[0]['reference']
            fail=first and ((kind=='retry' and operation.endswith(':pull:1'))
                           or (kind=='one-exhausted' and arguments[1]=='pull'))
            raw=RawExecution(status='failed' if fail else 'success',output='fixture pull result')
            if arguments[:2]==['image','inspect']:
                row=next(row for row in images if row['reference']==target)
                raw.output=json.dumps(['fixture@'+row['manifest_digest']])
                if kind=='bad-inspection' and first:
                    raw.output='not JSON'
            elapsed=time.perf_counter()-clock
            repo.finish_operation(operation,elapsed_seconds=elapsed)
            if kind=='indeterminate' and first:
                return None,elapsed
            return raw,elapsed

        module.command=substitute
        result=module.execute({'identity':'f'*64,'acquisition':{'images':images}})
        with ReceiptStore(local['ledger']) as store:
            after=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(old.authorization_id,)).fetchone())
            assert after==before
            assert not store._connection.execute("SELECT 1 FROM assessment_operations WHERE state='reserved'").fetchone()
        assert result['models']==result['services_started']==result['guest_programs_executed']==0
        assert result['passed']==(kind in {'success','retry'})
        if kind=='success':
            assert len(calls)==12 and result['grant_counters'][0]==13
        if kind=='retry':
            assert len(calls)==13 and result['grant_counters'][0]==14
        if kind=='one-exhausted':
            assert len(result['images'])==6 and sum(row['acquired'] for row in result['images'])==5
        if kind=='indeterminate':
            assert len(calls)==1 and result['cleanup_uncertain']
        if kind=='bad-inspection':
            assert len(calls)==12 and len(result['images'])==6 and not result['accounting_uncertain']
        return {'scenario':kind,'passed':True,'substituted_commands':len(calls),
                'old_counters_preserved':True,'unresolved_reservations':False}


if __name__=='__main__':
    results=[scenario(kind) for kind in ['success','retry','one-exhausted','bad-inspection','indeterminate']]
    value={'evidence_kind':'FIRST_PARTY_DRIVER_SUBSTITUTIONS_NOT_UPSTREAM_EXECUTION',
           'passed':True,'scenarios':results,'models':0,'docker_or_network_executed':False}
    (HERE/'acquisition-driver-controls.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value))
