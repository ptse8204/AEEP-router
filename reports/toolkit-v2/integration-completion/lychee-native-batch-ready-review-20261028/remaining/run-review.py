"""Run only an explicitly approved pinned link checker in the reviewed sandbox."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert len(sys.argv) == 2 and sha(OUT / 'operation-review.json') == sys.argv[1]
    review = json.loads((OUT / 'operation-review.json').read_text())
    approval = json.loads((OUT / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert sha(Path(__file__)) == review['runner_sha256']
    assert sha(ROOT / 'Makefile') == review['makefile_sha256']
    assert sha(ROOT / '.lychee.toml') == review['config_sha256']
    assert sha(OUT / 'sandbox-template.sb') == review['sandbox_template_sha256']
    assert verification_source_digest(ROOT)==review['source_digest']
    for name,expected in review['document_sha256'].items():assert sha(ROOT/name)==expected
    archive = Path(review['archive_path'])
    assert sha(archive) == review['archive_sha256']
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 100 * 1024**2
    assert json.loads((OUT / 'sandbox-preflight.json').read_text())['passed']
    assert not (OUT / 'execution-started.json').exists()
    runtime = Path(tempfile.mkdtemp(prefix='aeep-lychee-reviewed-', dir='/private/tmp')).resolve()
    result = {'review_sha256': sys.argv[1], 'runtime': str(runtime), 'model_calls': 0,
              'network_allowed': False, 'source_or_binary_redistribution': False,
              'automatic_retry': False, 'documents_are_data': True}
    immutable = {}
    began = time.monotonic()
    try:
        for name in ('home', 'tmp', 'bin'):
            (runtime / name).mkdir(mode=0o700)
        marker = runtime / 'operation.json'
        marker.write_text(json.dumps(result) + '\n')
        with tarfile.open(archive, mode='r:gz') as bundle:
            member = bundle.getmember(review['binary_member'])
            assert member.isfile() and member.size == review['binary_bytes']
            payload = bundle.extractfile(member).read()
        assert hashlib.sha256(payload).hexdigest() == review['binary_sha256']
        binary = runtime / 'bin' / 'lychee'
        binary.write_bytes(payload)
        binary.chmod(0o500)
        profile = (OUT / 'sandbox-template.sb').read_text()
        for key, value in {'HOME': runtime / 'home', 'TMP': runtime / 'tmp',
                           'ROOT': ROOT, 'AEEP': ROOT / '.aeep',
                           'GIT': ROOT / '.git', 'CODEX': ROOT / '.codex'}.items():
            profile = profile.replace('@' + key + '@', json.dumps(str(value)))
        profile_path = runtime / 'profile.sb'
        profile_path.write_text(profile)
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(runtime / 'home'),
                       'TMPDIR': str(runtime / 'tmp'), 'LC_ALL': 'en_US.UTF-8'}
        wrapper = runtime / 'lychee-sandbox'
        wrapper.write_text('#!' + sys.executable + '\n' +
            'import subprocess,sys\n' +
            'raise SystemExit(subprocess.run(' + repr([
                '/usr/bin/sandbox-exec', '-f', str(profile_path), str(binary)]) +
            '+sys.argv[1:],env=' + repr(environment) + ',timeout=60).returncode)\n')
        wrapper.chmod(0o500)
        immutable = {str(path): sha(path) for path in (marker, binary, profile_path, wrapper)}
        (OUT / 'execution-started.json').write_text(json.dumps(result, indent=2) + '\n')
        result['input_document_hashes'] = {name: sha(ROOT / name) for name in review['documents']}
        # The original standalone version call passed and is not replayed.
        prior=json.loads((OUT/'operation-review.json').read_text())['remaining_authority']
        original=Path(prior['original_version_file'])
        assert sha(original)==prior['original_version_sha256']
        assert original.read_text().strip()=='lychee 0.24.2'
        # Makefile performs its own version check and the exact offline link scan.
        with (OUT / 'docs-check.log').open('x') as log:
            run = subprocess.run(['make', 'docs-check', 'LYCHEE=' + str(wrapper)],
                                 cwd=ROOT, env={**os.environ, 'NPM_CONFIG_OFFLINE': 'true'},
                                 stdout=log, stderr=subprocess.STDOUT, timeout=180)
        result['docs_check_returncode'] = run.returncode
        result['passed'] = run.returncode == 0
    except BaseException as exc:
        result.update(passed=False, error_type=type(exc).__name__)
    finally:
        result['wall_seconds'] = time.monotonic() - began
        result['immutable_runtime_unchanged'] = bool(immutable) and all(
            Path(name).is_file() and not Path(name).is_symlink() and sha(Path(name)) == digest
            for name, digest in immutable.items())
        if result['immutable_runtime_unchanged']:
            # This private directory was created exclusively by this operation.
            shutil.rmtree(runtime)
            result['runtime_removed'] = not runtime.exists()
        else:
            result['runtime_removed'] = False
            result['preserved_for_review'] = str(runtime)
        result['free_after_bytes'] = shutil.disk_usage(ROOT).free
        (OUT / 'execution-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({key: value for key, value in result.items() if key != 'input_document_hashes'}))


main()
