"""Required read-only retained CI proofs and existing Node integration tests."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent / 'supplemental'
OUT.mkdir(exist_ok=True)
commands = [
    [sys.executable, 'scripts/check_assessment_policy.py'],
    [sys.executable, 'examples/economic_evidence/campaign.py', '--repetitions', '30', '--check', '--require-gates'],
    [sys.executable, 'examples/dsh_campaign/campaign.py', '--check'],
    [sys.executable, 'examples/dsh_campaign/live_campaign.py', '--check-report', 'reports/v05/dsh/live-safety.json'],
    [sys.executable, 'examples/dsh_campaign/live_campaign.py', '--check-comparison', 'reports/v05/dsh/live-comparison.json'],
    [sys.executable, 'examples/dsh_campaign/live_campaign.py', '--check-native-plan'],
    [sys.executable, 'examples/job_application/campaign.py', '--check'],
    [sys.executable, '-m', 'aeep.cli', 'provider', 'verify', 'examples/provider_package/aeep-provider.yaml', '-m', 'examples/provider_package/aeep.yaml', '--compact'],
    ['node', '--test', 'test.mjs', 'runtime.test.mjs'],
]
records = []
link = ROOT / 'integrations/dsh-aeep-router/node_modules'
existing = Path('/Users/edwintse/Documents/aeep-agent-router/integrations/dsh-aeep-router/node_modules')
assert not link.exists() and not link.is_symlink() and existing.is_dir()
pins = {}
for name in ('@deepseek-ai/dsh-llm', '@deepseek-ai/dsh-tools', '@deepseek-ai/schemastery'):
    path = existing / name / 'package.json'
    raw = path.read_bytes()
    data = json.loads(raw)
    pins[name] = {'version': data['version'], 'package_json_sha256': hashlib.sha256(raw).hexdigest(), 'license': data.get('license')}
(OUT / 'existing-node-dependencies.json').write_text(json.dumps({'path': str(existing), 'pins': pins, 'installed': False, 'downloads': 0}, indent=2) + '\n')
link.symlink_to(existing, target_is_directory=True)
try:
    for index, command in enumerate(commands):
        began = time.perf_counter()
        with (OUT / (str(index) + '.log')).open('x') as log:
            result = subprocess.run(command, cwd=ROOT if command[0] != 'node' else link.parent,
                env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')}, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        records.append({'argv': command, 'returncode': result.returncode, 'seconds': time.perf_counter() - began})
        (OUT / 'checks.json').write_text(json.dumps(records, indent=2) + '\n')
finally:
    if link.is_symlink() and Path(os.readlink(link)) == existing:
        link.unlink()
    (OUT / 'summary.json').write_text(json.dumps({'checks': len(records), 'all_passed': len(records) == len(commands)
        and all(item['returncode'] == 0 for item in records), 'temporary_link_removed': not link.exists(),
        'untrusted_software_installed': False, 'model_calls': 0, 'evidence_kind': 'retained_fixture_checks'}, indent=2) + '\n')
