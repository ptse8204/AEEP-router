"""Synthetic metadata/authority/redaction checks; never dispatch third-party code."""
import copy
import base64
from datetime import timedelta
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore
import run
import review_budget
from sanitize import self_check, validate_reply


def check_program_without_dispatch():
    namespace = {'__name__': 'first_party_diagnostic_synthetic_fixture'}
    exec(compile((run.HERE / 'diagnostic-program.py').read_text(), 'diagnostic-program.py', 'exec'), namespace)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as target:
        source = b'raise AssertionError("This synthetic subject must never be executed")\n'
        info = tarfile.TarInfo('tests/test_never_executed.py'); info.size = len(source)
        target.addfile(info, io.BytesIO(source))
    payload = {'python': '3.13', 'pytest': '8.3.5', 'wheels': [], 'pytest_plugins': [], 'source_modules': [],
        'archive': base64.b64encode(archive.getvalue()).decode(), 'archive_sha256': hashlib.sha256(archive.getvalue()).hexdigest(),
        'test_paths': ['tests/test_never_executed.py'], 'reviewed_identifiers': ['known']}
    cwd_paths = []
    stdin = sys.stdin
    try:
        for mode in ('error', 'timeout', 'over_limit'):
            def fake_run(argv, **kwargs):
                cwd_paths.append(kwargs['cwd'])
                assert argv[:3] == [sys.executable, '-B', '-c']
                assert kwargs['env']['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1' and kwargs['timeout'] == 22
                kwargs['stdout'].write(b"ModuleNotFoundError: No module named 'known'\nDO_NOT_RETAIN_SECRET\n")
                if mode == 'over_limit':
                    kwargs['stdout'].write(b'x' * 500_001)
                if mode == 'timeout':
                    raise namespace['subprocess'].TimeoutExpired(argv, 22)
                return SimpleNamespace(returncode=2)
            # Only our collector runs. The pytest/bootstrap subprocess is replaced
            # before calling it; neither pytest nor the synthetic subject runs.
            namespace['subprocess'] = SimpleNamespace(run=fake_run, TimeoutExpired=__import__('subprocess').TimeoutExpired,
                                                     STDOUT=__import__('subprocess').STDOUT)
            sys.stdin = io.StringIO(json.dumps(payload))
            reply = namespace['main']()
            validate_reply(reply, payload)
            assert 'DO_NOT_RETAIN_SECRET' not in json.dumps(reply)
            assert reply['timed_out'] == (mode == 'timeout')
            assert reply['log_limit_exceeded'] == (mode == 'over_limit')
            assert reply['diagnostics']['errors'][0]['missing_module'] == 'known'
            assert all(not path.exists() for path in cwd_paths)
    finally:
        sys.stdin = stdin
    return len(cwd_paths)


def main():
    review = json.loads((run.HERE / 'operation-review.json').read_text())
    async def forbidden(*args, **kwargs):
        raise AssertionError('Preparation attempted a contained invocation')
    run.invoke = forbidden
    run.validate_review(review)
    program_checks = check_program_without_dispatch()
    root = Path(tempfile.mkdtemp(prefix='aeep-diagnostic-definition-fixture-'))
    fixture = copy.deepcopy(review)
    store = ReceiptStore(root / 'synthetic-only.sqlite3')
    try:
        repo = AssessmentRepository(store)
        fake = AssessmentAuthorization(authorization_id='onboarding', subject_digests=[review['subject_digest']],
            recipe_digests=[content_digest(review['recipe'])],
            environment_digests=[g['request']['environment_digest'] for g in review['groups']],
            limits=AssessmentLimits(max_operations=100, max_elapsed_seconds=1000),
            expires_at=utc_now() + timedelta(minutes=5))
        repo.grant(fake)
        fixture['amendment']['authorization_digest'] = content_digest(fake)
        run.store_review(repo, fixture)
        for group in fixture['groups']:
            repo.authorize(RecipeMaterializationRequest.model_validate(group['request']))
        # Exercise the actual driver persistence path, then prove the bound limit.
        initial = [0, 0, 0.0, '0']
        original = review_budget.install(repo, store._connection, initial, review)
        request = RecipeMaterializationRequest.model_validate(fixture['groups'][0]['request'])
        for index in range(6):
            operation = 'synthetic-no-dispatch-' + str(index)
            repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=1), stage='synthetic_fixture_only')
            repo.finish_operation(operation, elapsed_seconds=0.001)
        try:
            repo.reserve(request, 'synthetic-seventh', AssessmentLimits(max_operations=1, max_elapsed_seconds=1), stage='synthetic_fixture_only')
        except RuntimeError:
            pass
        else:
            raise AssertionError('The actual installed driver budget allowed operation7')
        repo.reserve = original
    finally:
        store.close()
        import shutil
        shutil.rmtree(root)
    assert not root.exists()
    result = {'passed': True, 'same_driver_definition_persistence_and_authorization': True,
              'actual_driver_budget_rejects_operation7': True, 'synthetic_database_removed': True,
              'fixture_is_not_authority': True, 'sanitizer_guards': self_check(),
              'whole_collector_synthetic_checks_without_subprocess_dispatch': program_checks,
              'budget_guards': review_budget.self_check(), 'third_party_execution': False,
              'live_ledger_changed': False, 'new_models': 0}
    with (run.HERE / 'static-driver-check.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
