"""Verify real synthetic-worker records; illustrate arithmetic with separate fake bills."""
import json
import sqlite3
from pathlib import Path
from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt
from aeep_toolkit.cli import main
from aeep_toolkit.models import EvidenceBundle
from aeep_toolkit.reporting import render, summarize
from verify_controlled import verify
from test_toolkit_cash import fixture
from test_toolkit_reporting import bundle

root=Path.cwd()
out=Path(__file__).resolve().parent
controlled=root/'reports/toolkit-v2/c04/controlled-trials/attempt-5'
verification=verify(controlled)
connection=sqlite3.connect('file:'+str(controlled/'receipts.sqlite3')+'?mode=ro&immutable=1',uri=True)
try:
    receipts=[ExecutionReceipt.model_validate_json(row[0]) for row in connection.execute('SELECT payload_json FROM receipts')]
finally:
    connection.close()
records={content_digest(r):r.model_dump(mode='json') for r in receipts}
(out/'controlled-receipts.json').write_text(json.dumps(records,indent=2)+'\n')
value=EvidenceBundle.model_validate_json((controlled/'toolkit-evidence.json').read_text())
summary=summarize(value,accounting_records=records)
assert all(f['cash']['arms']['control']['complete_total'] is None for c in summary['cohorts'] for f in c['families'])
(out/'controlled-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(out/'controlled-report.html').write_text(render(summary,'html'))
# The following amounts are invented test inputs, kept separate from the worker receipts.
runs,records=fixture()
value=bundle()
value=EvidenceBundle.model_validate(value.model_dump()|{'runs':[r.model_dump()|{'receipt_refs':c.receipt_refs} for r,c in zip(value.runs,runs,strict=True)]})
fee={'amount':'10.00','period':'month','source_ref':'a'*64}
summary=summarize(value,accounting_records=records,recurring_fee=fee)
summary['limitations'].insert(0,'ARITHMETIC FIXTURE: all monetary amounts and the monthly fee in this example are invented test inputs, not actual bills or a developer price.')
assert summary['cohorts'][0]['families'][0]['cash']['break_even_scenario']['verified_successes_per_fee_period']==50
for name,facts in [('synthetic-evidence',value.model_dump(mode='json')),('synthetic-receipts',records),('synthetic-fee',fee),('synthetic-summary',summary)]:
    (out/(name+'.json')).write_text(json.dumps(facts,indent=2)+'\n')
(out/'synthetic-report.html').write_text(render(summary,'html'))
(out/'synthetic-report.md').write_text(render(summary,'markdown'))
print(json.dumps({'controlled_verification':verification,'controlled_cash':'unknown','arithmetic_example':'invented monetary test inputs only','synthetic_break_even':50}))
