"""Real isolated-home installer journey; retained results, no agent sign-in or calls."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    root.mkdir(parents=True, exist_ok=False)
    home, project = root / 'home', root / 'project'
    home.mkdir()
    project.mkdir()
    env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'AEEP_DATA_HOME': str(home / 'data'),
           'AEEP_CONFIG_HOME': str(home / 'config'), 'UV_PYTHON_PREFERENCE': 'only-managed'}
    installer = ['sh', str(args.release.resolve() / 'install.sh'), '--bundle', str(args.release.resolve() / 'bundle'),
                 '--agent', 'deepseek-api', '--project', str(project), '--yes']
    def run(argv: list[str]) -> str:
        result = subprocess.run(argv, env=env, cwd=project, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        print(result.stdout)
        result.check_returncode()
        return result.stdout
    run(installer)
    launcher = str(home / '.local/bin/aeep')
    manifest = home / 'config/config.yaml'
    saved = manifest.read_bytes()
    manifest.write_bytes(saved + b'\n# preserve operator edit\n')
    before = manifest.read_bytes()
    run(installer)
    assert manifest.read_bytes() == before
    matrix = json.loads(run([launcher, 'access', 'show', 'deepseek-api', '--json']))
    assert any(row['name'] == 'aeep_stack_recommend' and row['visible_in_aeep'] for row in matrix['tools'])
    run([launcher, 'access', 'deny', 'deepseek-api', 'aeep_stack_recommend', '--json'])
    exported = json.loads(run([launcher, 'tools', 'export', 'deepseek', '--connection', str(home / 'config/connections/deepseek-api.json')]))
    assert not any(row['function']['name'] == 'aeep_stack_recommend' for row in exported['tools'])
    run([launcher, 'access', 'allow', 'deepseek-api', 'aeep_stack_recommend', '--yes', '--json'])
    run([launcher, 'agents', 'disconnect', 'deepseek-api', '--yes', '--json'])
    run([launcher, 'uninstall', '--yes'])
    assert manifest.read_bytes() == before and not Path(launcher).exists()
    (root / 'result.json').write_text(json.dumps({'status': 'passed', 'checks': ['managed Python fallback', 'install', 'rerun', 'user edit preservation', 'denial and filtered exports', 'restore', 'disconnect', 'uninstall'], 'live_agent_checks': 'unverified', 'workspace': str(root)}, indent=2) + '\n')


if __name__ == '__main__':
    main()
