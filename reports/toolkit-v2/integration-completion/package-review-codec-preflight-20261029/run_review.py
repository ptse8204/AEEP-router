"""Three focused installed-artifact checks; exact approval required before apply."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, apply, digest, file_digest, remove

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-reviewed-digest')
    arguments = parser.parse_args()
    review = json.loads((HERE / 'operation-review.json').read_text())
    assert file_digest(Path(__file__)) == review['driver_sha256']
    assert verification_source_digest(ROOT) == review['source_digest']
    plan = RuntimeInstallation.model_validate_json((HERE / 'installation.json').read_text())
    assert digest(plan) == review['installation_sha256']
    for wheel in plan.wheels:
        path = Path(plan.wheelhouse) / wheel.filename
        assert path.is_file() and not path.is_symlink() and file_digest(path) == wheel.sha256
    for name, expected in review['inputs'].items():
        assert file_digest(ROOT / name) == expected
    if arguments.execute_reviewed_digest is None:
        print(json.dumps({'argument_policy_digest': digest(review), 'execution': False,
            'wheels': len(plan.wheels), 'checks': 3}))
        return
    assert arguments.execute_reviewed_digest == digest(review)
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == file_digest(HERE / 'operation-review.json')
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    assert shutil.disk_usage(plan.wheelhouse).free > 51 * 1024**3
    with (HERE / 'execution-started.json').open('x') as marker:
        json.dump({'review_sha256': approval['review_sha256'], 'automatic_retry': False}, marker)
    output = HERE / 'execution'
    output.mkdir(mode=0o700)
    checks = []

    def save():
        (output / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')

    started = time.monotonic()
    state = apply(plan, digest(plan))
    checks.append({'operation': 'apply', 'seconds': time.monotonic() - started, 'state': state})
    save()
    assert state['status'] == 'installed'
    runtime = Path(plan.destination)
    with tempfile.TemporaryDirectory(prefix='aeep-installed-codec-', dir=plan.wheelhouse) as temp:
        home = Path(temp).resolve()
        codec_check = home / 'installed-codec-check.py'
        shutil.copyfile(ROOT / review['codec_check'], codec_check)
        (home / 'review.json').write_text(json.dumps(review))
        profile = home / 'check.sb'
        profile.write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
            + f'(allow file-write* (subpath {json.dumps(str(home))}))\n'
            + '(allow file-write* (literal "/dev/null"))\n'
            + f'(deny file-read* (subpath {json.dumps(str(Path.home().resolve()))}))\n'
            + f'(allow file-read* (subpath {json.dumps(str(runtime))}))\n')
        prefix = ['/usr/bin/sandbox-exec', '-f', str(profile), str(runtime / 'bin/python'), '-I', '-B']
        environment = {'PATH': os.defpath, 'HOME': str(home), 'PYTHONNOUSERSITE': '1',
            'PYTHONDONTWRITEBYTECODE': '1', 'PIP_CONFIG_FILE': os.devnull, 'LC_ALL': 'C'}
        identity = '''import hashlib,importlib,json,sys
from pathlib import Path
from aeep_toolkit.cli import main
main(['list','essentials'])
assert 'aeep.router' not in sys.modules
review=json.load(open(sys.argv[1]))
for name,expected in review['installed_module_hashes'].items():
    assert hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest()==expected
from aeep.assessment import verification
value=verification.verification_source_digest(Path(verification.__file__).resolve().parents[3])
assert len(value)==64 and value!=hashlib.sha256().hexdigest()
print(json.dumps({'changed_modules_verified':2,'router_free_essentials_import':True,'installed_source_digest':value}))
'''
        commands = [('entrypoint', ['-m', 'aeep_toolkit', '--help']),
            ('installed-identity', ['-c', identity, str(home / 'review.json')]),
            ('codec-preflight', [str(codec_check)])]
        for label, arguments in commands:
            started = time.monotonic()
            process = subprocess.run([*prefix, *arguments], cwd=home, env=environment,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
            (output / (label + '.stdout')).write_text(process.stdout)
            (output / (label + '.stderr')).write_text(process.stderr)
            checks.append({'operation': label, 'returncode': process.returncode,
                'seconds': time.monotonic() - started})
            save()
            assert process.returncode == 0, label
    state = remove(plan, digest(plan))
    checks.append({'operation': 'remove', 'state': state})
    save()
    assert state['status'] == 'removed' and not runtime.exists()
    (output / 'summary.json').write_text(json.dumps({'source_commit': review['source_commit'],
        'source_digest': review['source_digest'], 'installed_checks': 3,
        'dependency_downloaded_bytes': 0, 'runtime_removed': True,
        'private_scratch_removed': not home.exists(), 'models': 0,
        'qualification_or_effectiveness_evidence': False}, indent=2) + '\n')
    print('Three focused installed checks and unchanged runtime removal passed.')


if __name__ == '__main__':
    main()
