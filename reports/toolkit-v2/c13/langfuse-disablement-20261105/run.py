"""Verify the unstarted disabled-export phase offline with the retained CLI."""

import argparse
import importlib.util
import json
import socket
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAST = HERE.parent/'langfuse-retained-budget-20261105'
sys.path.insert(1,str(LAST))
spec = importlib.util.spec_from_file_location('retained_langfuse_driver',LAST/'run.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
base = driver.base


def freeze():
    old = base.load(LAST/'operation-review.json')
    closed = base.load(LAST/'service-execution/summary.json')
    assert closed['stopped_phase']=='one local receipt export'
    assert not closed['cleanup_uncertain'] and not closed['accounting_uncertain']
    original = Path(old['cli_profile']).read_text()
    permitted = '(allow network-outbound (remote ip "localhost:39067"))\n'
    assert original.count(permitted)==1
    profile = HERE/'no-network.sb'
    profile.write_text(original.replace(permitted,''))
    reviewed = (HERE/'run.py', profile, LAST/'operation-review.json', LAST/'operator-approval.json',
                LAST/'service-execution/summary.json', LAST/'service-execution/stop-verdict.json')
    review = old | {
        'purpose':'Verify the first and still-unstarted disabled receipt-export check in a deny-all network sandbox.',
        'cli_profile':str(profile),'continuation_plan_id':HERE.name,
        'counters_before':closed['grant_counters'],
        'maximum_driver_commands':2,'maximum_additional_operations':4,
        'service_assets':old['service_assets']|{str(path):base.sha(path) for path in reviewed},
        'actions':['disabled-preview','disabled-check'],'service_start':False,'maximum_new_post_requests':0,
    }
    path = HERE/'operation-review.json'
    with path.open('x') as out:
        json.dump(review,out,indent=2);out.write('\n')
    base.write(HERE/'authority.json',{
        'review_sha256':base.sha(path), 'first_attempt':True,
        'underlying_review_sha256':old['runtime_approval_carried_from'],
        'reason':'The prior attempt stopped before either disabled CLI command. The check needs neither an active server nor credentials.',
        'standing_authority_sha256':base.sha(HERE.parent/'pipeline-standing-authority-20261104.json'),
    })
    print(base.sha(path))


def verify(review, identity):
    base.validate(review)
    assert not (HERE/'started.json').exists()
    closed = base.load(LAST/'service-execution/stop-verdict.json')
    assert closed['all_retained_stopped'] and closed['containers']==review['containers']
    with socket.socket() as sock:
        sock.settimeout(.3)
        assert sock.connect_ex(('127.0.0.1',base.PORT)) != 0
    with sqlite3.connect(Path(review['ledger']).as_uri()+'?mode=ro',uri=True) as db:
        assert driver.export_count(db,review['grant_authorization_id'])==1
        assert not db.execute("SELECT 1 FROM assessment_operations WHERE id LIKE '%:disabled-preview' OR id LIKE '%:disabled-check'").fetchone()
    out=HERE/'service-execution'
    out.mkdir(mode=0o700)
    base.HERE=HERE
    base.write(HERE/'started.json',{'review_sha256':identity,'service_start':False})
    prepared=base.load(driver.PRIOR/'prepared.json')
    request=base.RecipeMaterializationRequest.model_validate(prepared['request']).model_copy(
        update={'plan_id':review['continuation_plan_id']})
    with base.ReceiptStore(review['ledger']) as store:
        repo=base.AssessmentRepository(store)
        journey=base.Journey(review,repo,request,identity)
        assert journey.counters()==review['counters_before']
        result={'passed':False,'models':0,'comparisons':'PAUSED','service_started':False,'export_attempted':False}
        try:
            receipt=prepared['source_receipt_id']
            preview=journey.cli('disabled-preview','disabled-workflow.json','disabled-accounting.json',
                                receipt,configuration='software-engineering')
            assert not preview['enabled'] and not preview['export_performed']
            disabled=journey.cli('disabled-check','disabled-workflow.json','disabled-accounting.json',
                                 receipt,reviewed=preview['review_sha256'],configuration='software-engineering')
            assert disabled['status']=='disabled' and disabled['export_performed'] is False
            assert driver.export_count(store._connection,request.authorization_id)==1
            result.update(passed=True, disabled_export_verified=True, post_reservation_delta=0, network_profile='deny_all')
        except Exception as error:
            result['error_type']=type(error).__name__
        finally:
            result['grant_after']=journey.counters()
            result['accounting_uncertain']=bool(store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone())
            result['passed']=result['passed'] and not result['accounting_uncertain']
            base.write(out/'summary.json',result)
    print(json.dumps(result))
    return int(not result['passed'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--execute')
    args=parser.parse_args()
    if args.prepare:
        freeze()
    else:
        path=HERE/'operation-review.json'
        digest=base.sha(path)
        authority=base.load(HERE/'authority.json')
        assert args.execute==digest==authority['review_sha256'] and authority['first_attempt'] is True
        raise SystemExit(verify(base.load(path),digest))
