"""Bind the previously unstarted Invoice Fraud cases to the journaled executor."""

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent


def load(name):
    return json.loads(name.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(name, content):
    with (HERE / name).open('x') as stream:
        stream.write(content)


old_path = PARENT / 'reference-operation-review.json'
old = load(old_path)
terminal = PARENT / 'reference-execution/result.json'
ledger_path = terminal.with_name('ledger.json')
receipt_path = terminal.with_name('image.json')
failed, ledger, receipt = (load(path) for path in (terminal, ledger_path, receipt_path))
assert failed['review_sha256'] == sha(old_path) and failed['error_type'] == 'KeyError'
assert failed['operations'] == 2 and failed['unsettled_operations'] == 0 and not failed['containers']
assert receipt['metadata']['exit_code'] == 0 and receipt['metadata']['execution_evidence_ref'] is None
driver = PARENT / 'run-reference.py'
assert sha(driver) == old['files'][str(driver)]
new = driver.read_text()
new = new.replace("ROOT = HERE.parents[3]", "ROOT = HERE.parents[4]")
new = new.replace("authorization_id=HERE.name + '-reference'", "authorization_id=HERE.parent.name + '-reference-continuation'")
new = new.replace("authority = read(HERE / 'reference-delegated-authority.json')",
                  "authority = read(HERE / 'operator-approval.json')")
new = new.replace("and authority['first_attempt']", "and authority['approved'] is True")
new = new.replace("raw = await executor.execute(ExecutionContext(", "handle = await executor.start(ExecutionContext(")
new = new.replace("            evidence = ExecutionEvidence.model_validate", "                raw = await handle.task\n            evidence = ExecutionEvidence.model_validate")
start, end = new.index('            image_info = '), new.index('            report = ')
new = new[:start] + new[end:]
new = new.replace("""                state = json.loads(await command(name + '-stopped', ['inspect', '--format', '{{json .State}}', cid],
                                                 cleanup=True))""", """                state = {'Running': False, 'Status': 'stopped-by-engine',
                         'ExitCode': None, 'OOMKilled': None}""")
assert new.count('await executor.start(') == new.count('await handle.task') == 1
publish('run-reference.py', new)
path = HERE / 'run-reference.py'
settled_seconds = sum(row['elapsed_seconds'] for row in ledger['operations'])
old['files'].update({str(p): sha(p) for p in (old_path, terminal, ledger_path, receipt_path, path, Path(__file__))})
old.update(
    purpose='Run the five unstarted offline cases through the journaled command executor.',
    previous_review_sha256=sha(old_path), previous_charged_operations=failed['operations'],
    previous_charged_seconds=settled_seconds,
    max_operations=old['max_operations'] - failed['operations'],
    max_seconds=old['max_seconds'] - math.ceil(settled_seconds),
    expires_at=(datetime.now(UTC) + timedelta(days=2)).isoformat(),
    changes=[
        'Use BaseExecutor.start and await its journaled handle.',
        'Reuse the digest-pinned acquisition record and verify the image on each created container before guest start.',
        'If required, settle the final bounded stop using the successful engine stop return.',
    ],
)
publish('reference-operation-review.json', json.dumps(old, indent=2) + '\n')
print(sha(HERE / 'reference-operation-review.json'))
