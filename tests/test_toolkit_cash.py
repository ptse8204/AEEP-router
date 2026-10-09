"""Synthetic accounting records: arithmetic tests, not observed billing."""
from types import SimpleNamespace

import pytest

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt, utc_now
from aeep_toolkit.reporting import cash_summary, fee_break_even


def fixture(amounts=('0.30', '0.10'), successes=('pass','pass'), classification='verified'):
    records, runs = {}, []
    for arm, amount, success in zip(('control','treatment'),amounts,successes,strict=True):
        cash = {} if amount is None else {'status':'complete','components':[{'charge_id':arm,'amount':amount,'classification':classification,
                    'evidence':{'status':'complete','source':'operator_report','trust':'observed'}}]}
        receipt = ExecutionReceipt(decision_id=arm,action_id=arm,capability='fixture',executor_id=arm,executor_kind='command',status='success',
            started_at=utc_now(),ended_at=utc_now(),execution_success=True,estimated={},accounting={'cash':cash})
        ref = content_digest(receipt)
        records[ref] = receipt.model_dump(mode='json')
        runs.append(SimpleNamespace(run_id=arm,receipt_refs=(ref,),arm=arm,verification=success,retries=0,status='completed'))
    return runs, records


def test_decimal_totals_fee_and_zero_success():
    runs, records = fixture()
    fee = {'amount':'10.00','period':'month','source_ref':'a'*64}
    summary = cash_summary(runs,records,'USD',fee)
    assert summary['arms']['control']['complete_total'] == '0.30'
    assert summary['arms']['treatment']['cost_per_verified_success'] == '0.10'
    assert fee_break_even([dict(zip(('control','treatment'),runs,strict=True))],summary)['verified_successes_per_fee_period'] == 50
    runs[1].verification = 'fail'
    assert fee_break_even([dict(zip(('control','treatment'),runs,strict=True))],summary) is None
    assert cash_summary(runs,records,'USD')['arms']['treatment']['cost_per_verified_success'] is None


@pytest.mark.parametrize('amounts,classification', [(('0.3',None),'verified'),(('0.3','0.1'),'estimated')])
def test_missing_or_estimated_is_not_actual(amounts,classification):
    runs,records = fixture(amounts,classification=classification)
    summary = cash_summary(runs,records,'USD',{'amount':'10','period':'month','source_ref':'a'*64})
    assert summary['arms']['treatment']['complete_total'] is None
    assert fee_break_even([dict(zip(('control','treatment'),runs,strict=True))],summary) is None


def test_zero_cash_is_distinct_from_missing_and_zero_savings_has_no_break_even():
    runs,records = fixture(('0','0'))
    summary = cash_summary(runs,records,'USD',{'amount':'10','period':'year','source_ref':'a'*64})
    assert summary['arms']['treatment']['complete_total'] == '0'
    assert fee_break_even([dict(zip(('control','treatment'),runs,strict=True))],summary) is None


def test_reference_tampering_missing_shared_receipts_and_charges_rejected():
    runs,records = fixture()
    with pytest.raises(ValueError):
        cash_summary(runs,{},'USD')
    with pytest.raises(ValueError):
        cash_summary([runs[0],runs[0]],records,'USD')
    ref = runs[1].receipt_refs[0]
    records[ref]['accounting']['cash']['components'][0]['amount'] = '99'
    with pytest.raises(ValueError):
        cash_summary(runs,records,'USD')
    newref = content_digest(ExecutionReceipt.model_validate(records[ref]))
    records[newref] = records[ref]
    runs[1].receipt_refs = (newref,)
    records[newref]['accounting']['cash']['components'][0]['charge_id'] = 'control'
    latest = content_digest(ExecutionReceipt.model_validate(records[newref]))
    records[latest] = records[newref]
    runs[1].receipt_refs = (latest,)
    with pytest.raises(ValueError,match='shared charge'):
        cash_summary(runs,records,'USD')


@pytest.mark.parametrize('amount',['NaN','Infinity','-1'])
def test_invalid_fee_rejected(amount):
    runs,records = fixture()
    with pytest.raises(ValueError):
        cash_summary(runs,records,'USD',{'amount':amount,'period':'month','source_ref':'a'*64})


def test_wrong_currency_and_ungraded_results_stay_unknown():
    runs,records = fixture()
    assert cash_summary(runs,records,'EUR')['arms']['control']['complete_total'] is None
    runs[0].verification = 'unknown'
    assert cash_summary(runs,records,'USD')['arms']['control']['cost_per_verified_success'] is None


def test_no_verified_success_has_no_fee_payback():
    runs,records = fixture(successes=('fail','fail'))
    summary = cash_summary(runs,records,'USD',{'amount':'10','period':'month','source_ref':'a'*64})
    assert fee_break_even([dict(zip(('control','treatment'),runs,strict=True))],summary) is None


def test_ambiguous_retry_and_unresolved_run_cannot_claim_complete_cash():
    runs,records = fixture()
    runs[0].retries = 1
    with pytest.raises(ValueError,match='retry receipts'):
        cash_summary(runs,records,'USD')
    runs[0].retries = 0
    runs[0].status = 'indeterminate'
    assert cash_summary(runs,records,'USD')['arms']['control']['complete_total'] is None


def test_failure_costs_are_included_in_cost_per_success():
    runs,records = fixture()
    failed, extra = fixture(('0.70','0.30'),successes=('fail','fail'))
    for run in failed:
        old = run.receipt_refs[0]
        receipt = extra[old]
        receipt['accounting']['cash']['components'][0]['charge_id'] += '-failed'
        ref = content_digest(ExecutionReceipt.model_validate(receipt))
        records[ref] = receipt
        run.receipt_refs = (ref,)
        run.run_id += '-failed'
    summary = cash_summary([*runs,*failed],records,'USD')
    assert summary['arms']['control']['cost_per_verified_success'] == '1.00'
    assert summary['arms']['treatment']['cost_per_verified_success'] == '0.40'


def test_cli_costs_are_explicit_synthetic_and_missing_exposure_blocks_fee(tmp_path,capsys):
    import json

    from test_toolkit_reporting import bundle

    from aeep_toolkit.cli import main
    from aeep_toolkit.models import EvidenceBundle
    value = bundle()
    runs,records = fixture()
    value = EvidenceBundle.model_validate(value.model_dump() | {'runs':[r.model_dump() | {'receipt_refs':c.receipt_refs} for r,c in zip(value.runs,runs,strict=True)]})
    evidence,accounting,fee = [tmp_path/name for name in ('bundle.json','receipts.json','fee.json')]
    evidence.write_text(value.model_dump_json())
    accounting.write_text(json.dumps(records))
    fee.write_text(json.dumps({'amount':'10','period':'month','source_ref':'a'*64}))
    args = ['report','--evidence',str(evidence),'--accounting',str(accounting),'--recurring-fee',str(fee),'--format','json']
    assert main(args) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['outcome'] == 'NOT_ASSESSED'
    family = summary['cohorts'][0]['families'][0]
    assert family['cash']['break_even_scenario']['verified_successes_per_fee_period'] == 50
    assert main([*args[:-1], 'html']) == 0
    rendered = capsys.readouterr().out
    assert 'evidence kind: synthetic' in rendered
    assert 'not observed charges' in rendered
    value.runs[1].candidate_exposed = None
    evidence.write_text(value.model_dump_json())
    assert main(args) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['cohorts'][0]['families'][0]['cash']['break_even_scenario'] is None
