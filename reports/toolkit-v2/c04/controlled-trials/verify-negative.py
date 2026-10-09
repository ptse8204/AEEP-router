"""Verify actual retained fixture evidence; corrupt only task-owned temporary copies."""
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

from verify_controlled import verify

source = Path('reports/toolkit-v2/c04/controlled-trials/attempt-5').resolve()
assert verify(source)['verified_trials'] == 4
results = []
for attack in ('summary', 'artifact', 'receipt', 'event', 'ledger'):
    with tempfile.TemporaryDirectory(prefix='aeep-controlled-verifier-') as name:
        copied = Path(name)/'evidence'
        shutil.copytree(source,copied)
        if attack == 'summary':
            p=copied/'summary.json'; data=json.loads(p.read_text()); data['cohorts']=[]; p.write_text(json.dumps(data))
        elif attack == 'artifact':
            next((copied/'upstream').rglob('output.txt')).write_text('changed synthetic artifact')
        elif attack == 'ledger':
            p=copied/'result.json'; data=json.loads(p.read_text()); data['ledger']['operations'][0]['elapsed_seconds']=0; p.write_text(json.dumps(data))
        else:
            db=sqlite3.connect(copied/'receipts.sqlite3')
            if attack == 'receipt':
                db.execute("UPDATE receipts SET payload_json='{}'")
            else:
                db.execute("DELETE FROM assessment_records WHERE kind='execution_event'")
            db.commit();db.close()
        try:
            verify(copied)
        except ValueError:
            results.append({'altered':attack,'rejected':True})
        else:
            raise AssertionError(attack+' unexpectedly accepted')
assert verify(source)['verified_trials']==4
print(json.dumps({'original_still_valid':True,'checks':results},indent=2))
