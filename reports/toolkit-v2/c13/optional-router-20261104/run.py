"""Run the existing optional StackRuntime through its ordinary operator CLI."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
raw = (HERE / 'operation-review.json').read_bytes()
review = json.loads(raw)
authority = json.loads((HERE / 'delegated-authority.json').read_bytes())
digest = hashlib.sha256(raw).hexdigest()
assert args.execute_delegated == authority['review_sha256'] == digest and authority['first_attempt']
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
work = Path(review['work'])
assert not (work / 'state.db').exists()
assert shutil.disk_usage(work).free >= 50 * 1024**3
for name, sha in review['assets'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name

sys.path.insert(0, review['snapshot_verifier_source'])
from aeep_toolkit.install_runtime import snapshot

runtime = Path(review['installed_runtime'])
assert snapshot(runtime) == review['installed_runtime_snapshot']
with (HERE / 'execution-started.json').open('x') as f:
    json.dump({'review_sha256': digest, 'models': 0}, f)

env = {
    'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'),
    'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
}
prefix = ['/usr/bin/sandbox-exec', '-f', str(HERE / 'cli.sb'),
          review['python'], '-I', '-B', '-m']
records = []


def invoke(module, group, *options):
    assert len(records) < review['maximum_cli_invocations']
    assert shutil.disk_usage(work).free >= 50 * 1024**3
    command = [*prefix, module, group, '-m', str(work / 'manifest.json'), *options]
    if module == 'aeep_toolkit':
        command = [*prefix, module, group, *options]
    started = time.perf_counter()
    process = subprocess.run(command, env=env, cwd=work, capture_output=True, text=True,
                             timeout=review['command_timeout_seconds'])
    records.append({'command': command, 'exit_code': process.returncode,
                    'wall_seconds': time.perf_counter() - started,
                    'stdout_sha256': hashlib.sha256(process.stdout.encode()).hexdigest(),
                    'stderr_sha256': hashlib.sha256(process.stderr.encode()).hexdigest()})
    assert process.returncode == 0, 'CLI command failed: ' + str(options[:1])
    return json.loads(process.stdout)


def receipts():
    db = work / 'state.db'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        return [json.loads(row[0]) for row in conn.execute('SELECT payload_json FROM receipts')]


result = {'passed': False, 'models': 0, 'provider_calls': 0,
          'comparisons': 'PAUSED', 'canonical_route_receipts': []}
try:
    proposal = invoke('aeep', 'stack', 'propose', str(work / 'goal.json'))
    proposal_id = proposal['proposal_id']
    before = invoke('aeep', 'stack', 'preflight', proposal_id)
    assert not before['ready'] and not receipts()
    # The exact proposal is derived from the pinned manifest and goal.
    ref = before['proposal_digest']
    result['proposal_digest'] = ref
    review_output = invoke('aeep', 'assess', 'review', ref)
    assert review_output == {'digest': ref, 'reviewed': True}
    after = invoke('aeep', 'stack', 'preflight', proposal_id)
    assert after['ready'] and after['proposal_digest'] == ref
    assembled = invoke('aeep', 'stack', 'assemble', proposal_id)
    assert assembled['assembled'] and not assembled['activated']
    executed = invoke('aeep', 'stack', 'run', proposal_id, str(work / 'inputs.json'))
    assert executed['status'] == 'complete'
    assert json.loads(executed['outputs']['verify']['artifact']) == {
        'grand_total': 25, 'row_count': 3, 'totals': {'A': 17, 'B': 8}, 'verified': True,
    }
    rows = receipts()
    assert len(rows) == len(executed['receipt_ids']) == 4
    assert {row['receipt_id'] for row in rows} == set(executed['receipt_ids'])
    assert all(row['status'] == 'success' and row['execution_success'] for row in rows)
    counts = len(rows)
    basic = invoke('aeep_toolkit', 'list', 'essentials')
    assert basic['selected'] == [] and all(x['id'] != 'aeep-router' for x in basic['catalog'])
    assert len(receipts()) == counts
    result.update(passed=True, unreviewed_preflight_denied=True,
                  standing_activation_created=False, basic_catalog_router_inert=True,
                  artifact_sha256=hashlib.sha256(executed['outputs']['verify']['artifact'].encode()).hexdigest(),
                  canonical_route_receipts=[
                      {'receipt_id': row['receipt_id'], 'executor': row['executor_id'],
                       'status': row['status'], 'receipt_sha256': hashlib.sha256(
                           json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                       'latency_ms': row['actual_resources'].get('latency_ms')}
                      for row in rows
                  ])
except Exception as error:
    result.update(error_type=type(error).__name__, first_party_error=str(error)[:200])
finally:
    result['retained_runtime_unchanged'] = snapshot(runtime) == review['installed_runtime_snapshot']
    result['passed'] = result['passed'] and result['retained_runtime_unchanged']
    result['cli_intervals'] = records
    result['accounting'] = 'Separate CLI wall durations and canonical node receipts. CLI run contains node execution. Do not add their durations.'
    result['fixture_scope'] = 'Actual Router/StackRuntime execution on the existing synthetic data example. No upstream task, model or usefulness claim.'
    (HERE / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'cli_intervals'}))
raise SystemExit(not result['passed'])
