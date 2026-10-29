"""Run one explicitly approved, finite source-reproduction attempt; no retries."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

from aeep.assessment.verification import verification_source_digest
from review_bindings import audit, sha

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    assert len(sys.argv) == 2 and sha(HERE / 'operation-review.json') == sys.argv[1]
    review = json.loads((HERE / 'operation-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert verification_source_digest(ROOT) == review['source_digest']
    bindings = audit([HERE / 'operation-review.json'], ROOT)
    assert bindings['passed'], bindings['errors']
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3
    out = HERE / 'runtime-execution'
    assert not (HERE / 'execution-started.json').exists() and not (out / 'execution-started.json').exists()
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as db:
        counters = list(db.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    save(HERE / 'execution-started.json', {'review_sha256': sys.argv[1], 'automatic_retry': False})
    with (out / 'operation-review.json').open('xb') as stream:
        stream.write((HERE / 'operation-review.json').read_bytes())
    save(out / 'operator-approval.json', {**approval, 'parent_review_sha256': sys.argv[1],
        'authority': 'Exact parent approval covers this identical review and its frozen source calls. Mechanical binding,not a new human reply.'})
    anchor = review.get('cumulative_grant_anchor', counters)
    assert counters[0] >= anchor[0] and counters[1] == anchor[1] and counters[2] >= anchor[2] and counters[3] == anchor[3]
    save(out / 'review-budget-anchor.json', {'grant_before': anchor})
    canary = ROOT / review['host_canary']
    marker = b'AEEP owned source-audit canary; no secret.\n'
    assert not canary.exists()
    with canary.open('xb') as stream:
        stream.write(marker)
    summary = {'review_sha256': sys.argv[1], 'batch_completed': False, 'model_turns': 0,
        'cash_usd': '0', 'new_builds_installs_downloads': 0, 'automatic_retry': False}
    try:
        for name in ('run.py', 'audit-execution.py'):
            with (HERE / (name + '.log')).open('x') as log:
                done = subprocess.run([sys.executable, str(out / name), *([sys.argv[1]] if name == 'run.py' else [])],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    timeout=review['maximum_reserved_seconds'] + 60)
            assert done.returncode == 0, 'Terminal driver failure;reconcile before any further dispatch'
        result = json.loads((out / 'completion-audit.json').read_text())
        assert result['batch_completed'] and result['physical_receipt_integrity_passed']
        assert result['all_owned_containers_absent']
        summary.update(batch_completed=True, eligible_cases=result['eligible_cases'],
            canonical_operations=result['canonical_operations'],
            canonical_receipts_reopened=result['canonical_receipts_reopened'],
            grant_after=result['grant_after'], conformance_mode='exact_current_backend_reuse',
            new_runtime_probes=result['new_runtime_probes'], qualification=False, comparative_usefulness=False, selection=False)
    except BaseException as error:
        summary['error_type'] = type(error).__name__
        raise
    finally:
        assert canary.is_file() and not canary.is_symlink() and canary.read_bytes() == marker
        canary.unlink()
        save(HERE / 'canary-cleanup.json', {'unchanged_owned_canary_removed': True})
        summary['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        save(HERE / 'execution-result.json', summary)


if __name__ == '__main__':
    main()
