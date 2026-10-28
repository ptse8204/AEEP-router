"""Authored host fixtures only. Public repository sources never execute here."""
import base64
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from aeep.assessment.repository_suites import pack_files
from stable_profile import REPOSITORY, compile_profile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREVIOUS = HERE.parent / 'repository-native-batch-ready-20261028'


def main():
    original = (PREVIOUS / 'observer-operator.py').read_text()
    operator = compile_profile(original)
    default = operator.replace('OPERATOR_REVIEW = True', 'OPERATOR_REVIEW = False')
    assert operator != default and operator.count(REPOSITORY) == 1
    for bad in (original.replace("repo.mkdir()", "repo.mkdir(exist_ok=True)"),
                original + "\n        repo = root / 'repository'\n        repo.mkdir()"):
        try:
            compile_profile(bad)
        except (ValueError, AssertionError, SyntaxError):
            pass
        else:
            raise AssertionError('Changed creation contract accepted')
    source = '''import traceback,pytest,os,stat
try:
    raise ValueError('authored traceback parameter')
except ValueError as error:
    frame=traceback.format_tb(error.__traceback__)[0].strip()
@pytest.mark.parametrize('value',[frame],ids=str)
def test_path(value):
    assert __file__ in value
    assert stat.S_IMODE(os.stat(os.path.dirname(os.path.dirname(__file__))).st_mode)==0o700
'''
    archive = pack_files({'tests/test_fixed.py': source.encode()})
    payload = {'archive': base64.b64encode(archive).decode(),
        'archive_sha256': hashlib.sha256(archive).hexdigest(),
        'python': '.'.join(map(str, sys.version_info[:2])),
        'pytest': importlib.metadata.version('pytest'), 'wheels': [],
        'test_paths': ['tests/test_fixed.py']}
    with tempfile.TemporaryDirectory(prefix='aeep-AUTHORED-stable-profile-', dir=ROOT / '.aeep') as temp:
        scratch = Path(temp)
        owned_repo = scratch / 'repository'

        def run(program, request):
            # This authored host fixture replaces the one fixed contained path
            # with its own private scratch. It cannot select a worker host path.
            fixture = program.replace(repr(REPOSITORY), repr(str(owned_repo)))
            child = subprocess.run([sys.executable, '-B', '-c', fixture],
                input=json.dumps(request), text=True, capture_output=True,
                cwd=scratch, timeout=30)
            return child

        collection = run(operator, {**payload, 'collect_only': True})
        assert collection.returncode == 0, collection.stderr
        names = json.loads(collection.stdout)['collection']['native_ids']
        assert len(names) == 1 and str(owned_repo) in names[0]
        # Existing paths must fail closed, preserving their contents.
        marker = owned_repo / 'owned-fixture-marker'
        marker.write_text('preserve this authored marker')
        conflict = run(operator, payload)
        assert conflict.returncode != 0 and 'FileExistsError' in conflict.stderr
        assert marker.read_text() == 'preserve this authored marker'
        shutil.rmtree(owned_repo)  # Only this fixture's authored tree.
        evaluation = run(operator, payload)
        assert evaluation.returncode == 0, evaluation.stderr
        observed = json.loads(evaluation.stdout)['evaluation']
        assert observed['exit_code'] == 0 and observed['statuses'] == {names[0]: 'PASSED'}
        shutil.rmtree(owned_repo)
        raw = run(default, payload)
        assert raw.returncode == 0, raw.stderr
        assert json.loads(raw.stdout) == observed
        shutil.rmtree(owned_repo)
        denied = run(default, {**payload, 'collect_only': True})
        assert denied.returncode != 0 and not denied.stdout.strip()
        # A preexisting symlink is never followed or removed by the profile.
        outside = scratch / 'other-owned-directory'
        outside.mkdir()
        (outside / 'marker').write_text('preserve')
        owned_repo.symlink_to(outside, target_is_directory=True)
        symlink = run(operator, payload)
        assert symlink.returncode != 0 and 'FileExistsError' in symlink.stderr
        assert (outside / 'marker').read_text() == 'preserve'
    assert not scratch.exists()
    (HERE / 'observer-operator.py').write_text(operator)
    (HERE / 'observer-default.py').write_text(default)
    result = {'passed': True, 'authored_fixture_only': True,
        'checks': ['exact_two_site_AST_delta', 'changed_creation_site_rejected',
            'duplicate_creation_site_rejected', 'traceback_identity_stable_across_fresh_processes',
            'all_phases_passed', 'private_directory_mode_0700',
            'existing_path_rejected_and_preserved', 'default_raw_reply_equivalent',
            'default_collection_denied', 'existing_symlink_rejected_and_preserved'],
        'contained_repository_literal': REPOSITORY,
        'host_fixture_root_override_only': True, 'all_owned_scratch_removed': True,
        'public_sources_executed': 0, 'models_installs_builds_downloads': 0,
        'target_container_conformance_or_repository_grade': False,
        'operator_sha256': hashlib.sha256(operator.encode()).hexdigest(),
        'default_sha256': hashlib.sha256(default.encode()).hexdigest()}
    (HERE / 'stable-profile-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
