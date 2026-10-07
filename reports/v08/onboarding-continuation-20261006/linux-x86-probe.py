"""Linux installer acceptance with a pre-existing image and no installed Python."""
import hashlib
import json
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
report = Path(__file__).parent
workspace = Path('/tmp/aeep-onboarding-continuation/linux-x86')
image = 'ubuntu@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90'
name = 'aeep-onboarding-linux-x86-20261006'
command = '''set -eu
uname -sm
if command -v python python3; then echo 'Unexpected Python in bootstrap image'; exit 2; fi
mkdir -p /evidence/project /evidence/home
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl ca-certificates
dpkg-query -W > /evidence/os-packages.tsv
env HOME=/evidence/home AEEP_DATA_HOME=/evidence/home/data AEEP_CONFIG_HOME=/evidence/home/config sh /release/install.sh --bundle /release/bundle --agent deepseek-api --project /evidence/project --yes
/evidence/home/data/venv/bin/python /check_installer.py --release /release --workspace /evidence/journey
'''
argv = ['docker', 'create', '--name', name, '--pull', 'never', '--platform', 'linux/amd64', '--security-opt', 'no-new-privileges',
        '--memory', '2g', '--cpus', '2', '--mount', f'type=bind,source={workspace},target=/evidence',
        '--mount', f'type=bind,source={repo / "dist/v0.8.2-onboarding-continuation"},target=/release,readonly',
        '--mount', f'type=bind,source={repo / "scripts/check_installer.py"},target=/check_installer.py,readonly',
        '--entrypoint', '/bin/sh', image, '-c', command]
container = subprocess.check_output(argv, text=True).strip()
record = {'image_id': image, 'existing_tag': 'ubuntu:24.04', 'container': container,
          'name': name, 'workspace': str(workspace), 'scope': 'Linux x86_64 container under emulation; not WSL or physical x86 hardware',
          'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'argv': argv}
(report / 'linux-x86-resources.json').write_text(json.dumps(record, indent=2) + '\n')
with (report / 'linux-x86.log').open('w') as log:
    result = subprocess.run(['docker', 'start', '-a', container], stdout=log, stderr=subprocess.STDOUT, timeout=900)
record['exit_code'] = result.returncode
record['status'] = 'passed' if result.returncode == 0 else 'failed'
record['container_state'] = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Status}}', container], text=True).strip()
if (workspace / 'journey/result.json').exists():
    record['journey'] = json.loads((workspace / 'journey/result.json').read_text())
(report / 'linux-x86-result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
result.check_returncode()
