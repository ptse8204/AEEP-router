"""Record completed frozen validation logs without rerunning any checks."""
import datetime
import hashlib
import json
import re
from pathlib import Path
from aeep.assessment.verification import verification_source_digest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = '449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad'
LOCK = '2fc3c9cd8b21ca23f175e5465d6b83c8d139388a3d513bbb50347221ed74bf71'
assert verification_source_digest(ROOT) == SOURCE
assert hashlib.sha256((ROOT / 'reports/v08/verification-lock.json').read_bytes()).hexdigest() == LOCK
checks = []
for name, argv in json.loads((OUT / 'commands.json').read_text()):
    path = OUT / (name + '.log')
    raw = path.read_text()
    assert '\nEXIT_CODE: 0\n' in raw, name
    assert 'VERIFICATION_SOURCE_DIGEST_AFTER: ' + SOURCE in raw, name
    assert 'VERIFICATION_LOCK_SHA256_AFTER: ' + LOCK in raw, name
    checks.append({'name': name, 'argv': argv, 'exit_code': 0, 'log_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
counts = {}
for name in ('10-pytest', '11-coverage-run'):
    lines = (OUT / (name + '.log')).read_text().splitlines()
    counts[name] = next(line for line in reversed(lines) if re.search(r'\b\d+ passed, \d+ skipped', line))
coverage = json.loads((OUT / 'coverage.json').read_text())['totals']
value = {'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_digest': SOURCE,
    'verification_lock_sha256': LOCK, 'status': 'all_commands_passed', 'command_count': len(checks),
    'commands': checks, 'pytest_summaries': counts, 'coverage_totals': coverage,
    'scope': 'Offline software validation; real model/native/container opt-ins were cleared. Skips do not establish live or boundary gates.',
    'source_unchanged': True, 'temporary_resources_retained': True,
    'temporary_root': '/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/aeep-luna-b-three-role-validation-20261003',
    'canonical_assessment_grant_used': False, 'remaining': ['Current composed boundary conformance', 'Matching live qualification', 'Original three-way AEEP-value campaign', 'Independent production/adoption gates']}
path = OUT / 'terminal-summary.json'
with path.open('x') as stream:
    json.dump(value, stream, indent=2)
    stream.write('\n')
print(json.dumps({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'command_count': len(checks), 'pytest': counts, 'coverage': coverage}))
