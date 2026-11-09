"""Retry the reference with bounded diagnostics and gate the four unstarted controls."""

import argparse
import asyncio
import json
import runpy
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt, ResourceVector, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
runner = runpy.run_path(str(HERE / 'run-calibration.py'))
read, sha, save, context, classify, Scope = (runner[key] for key in ('read', 'sha', 'save', 'context', 'classify', 'Scope'))
ROOT, PRIVATE, ORIGINAL, CASES = (runner[key] for key in ('ROOT', 'PRIVATE', 'PROTECTED', 'CASES'))
STAGED = PRIVATE / 'protected-continuation'
OUT = HERE / 'continuation'
REVIEW = OUT / 'operation-review.json'
GRANT = 'skillsbench-prefix-cache-reference-continuation-20261109'
STAGES = {'bootstrap', 'copy_inputs', 'run_oracle', 'load_report', 'mutate_report', 'import_pytest', 'run_pytest', 'parse_junit'}
TYPES = {'AssertionError', 'FileNotFoundError', 'PermissionError', 'RuntimeError', 'TimeoutExpired',
         'JSONDecodeError', 'ModuleNotFoundError', 'ParseError', 'OSError', 'KeyError', 'ValueError', 'SystemExit'}


def replace(source, old, new):
    assert source.count(old) == 1
    return source.replace(old, new)


def updated_guest():
    source = (ORIGINAL / 'calibrate.py').read_text()
    source = replace(source, 'def main():', "STAGE = 'bootstrap'\n\n\ndef main():\n    global STAGE")
    for marker, stage in (
        ('    for path in PATHS[:2]:', 'copy_inputs'),
        ("    oracle = subprocess.run", 'run_oracle'),
        ('    initial = json.loads', 'load_report'),
        ("    if case == 'incomplete':", 'mutate_report'),
        ('    import pytest', 'import_pytest'),
        ('    runner = pytest.main', 'run_pytest'),
        ('    document = ET.parse', 'parse_junit'),
    ):
        source = replace(source, marker, f'    STAGE = {stage!r}\n'+marker)
    source = replace(source, "        main()\n", """        try:
            main()
        except (Exception, SystemExit) as error:
            name = type(error).__name__
            names = """+repr(sorted(TYPES))+"""
            if WORK.is_dir():
                (WORK / 'result.json').write_text(json.dumps({
                    'case': sys.argv[1], 'diagnostic_stage': STAGE,
                    'diagnostic_type': name if name in names else 'Other',
                }))
            else:
                print(json.dumps({'case': sys.argv[1], 'diagnostic_stage': STAGE,
                                  'diagnostic_type': name if name in names else 'Other'}))
""")
    source = replace(source, """        if result.returncode or not (WORK / 'result.json').is_file():
            raise SystemExit('protected guest stopped before emitting its grade')
        print((WORK / 'result.json').read_text())
""", """        if result.returncode:
            raise SystemExit('protected guest stopped before emitting its grade')
        if (WORK / 'result.json').is_file():
            print((WORK / 'result.json').read_text())
        else:
            failure = json.loads(result.stdout)
            assert set(failure) == {'case', 'diagnostic_stage', 'diagnostic_type'}
            print(json.dumps(failure))
""")
    compile(source, 'calibrate.py', 'exec')
    return source.encode()


def configure():
    context.__globals__.update(PROTECTED=STAGED, GRANT=GRANT)


def validate_prior():
    prior = read(HERE / 'calibration-review.json')
    outcome = read(HERE / 'calibration-result.json')
    receipt = read(HERE / 'reference-receipt.json')
    assert outcome['review_sha256'] == sha(HERE / 'calibration-review.json')
    assert outcome['accounting_settled'] and outcome['operations'] == 1 and not outcome['passed']
    assert not outcome['cases'] and outcome['models'] == 0
    assert receipt['error_type'] == 'CommandExitError'
    assert all(sha(name) == digest for name, digest in prior['pins'].items())
    assert runner['verification_source_digest'](ROOT) == prior['source_sha256']
    return prior


def freeze():
    prior = validate_prior()
    OUT.mkdir()
    STAGED.mkdir(mode=0o755)
    for source in sorted(ORIGINAL.iterdir()):
        target = STAGED / source.name
        data = updated_guest() if source.name == 'calibrate.py' else source.read_bytes()
        with target.open('xb') as stream:
            stream.write(data)
        target.chmod(0o444)
    STAGED.chmod(0o555)
    configure()
    environment = runner['checked_environment']()
    pins = {name: digest for name, digest in prior['pins'].items() if Path(name).parent != ORIGINAL}
    paths = [Path(__file__).resolve(), HERE / 'calibration-review.json', HERE / 'calibration-result.json',
             HERE / 'reference-receipt.json', HERE / 'calibration-ledger.json', *sorted(STAGED.iterdir())]
    pins.update({str(p): sha(p) for p in paths})
    review = prior | {'purpose': 'One protected reference retry with failure stages, then four unstarted controls.',
        'pins': pins, 'previous_review_sha256': sha(HERE / 'calibration-review.json'),
        'environment_sha256': content_digest(environment),
        'executors': {case: content_digest(runner['spec_for'](case)) for case in CASES},
        'original_solver_and_test_bytes_preserved': True, 'retains_prior_charge': True,
        'maximum_operations': 5, 'maximum_reserved_seconds': 275,
        'expires_at': (utc_now() + timedelta(hours=18)).isoformat()}
    save(REVIEW, review)
    preflight(review)
    print(sha(REVIEW))


def preflight(review):
    prior = validate_prior()
    for path in sorted(STAGED.iterdir()):
        source = ORIGINAL / path.name
        if path.name == 'calibrate.py':
            assert path.read_bytes() == updated_guest()
        else:
            assert sha(path) == prior['pins'][str(source)]
    configure()
    return runner['preflight'](review)


def checked_failure(case, facts):
    if 'diagnostic_stage' not in facts:
        return None
    assert set(facts) == {'case', 'diagnostic_stage', 'diagnostic_type'} and facts['case'] == case
    assert facts['diagnostic_stage'] in STAGES and facts['diagnostic_type'] in TYPES | {'Other'}
    return facts


async def execute(digest):
    review = read(REVIEW)
    assert digest == sha(REVIEW) and read(OUT / 'approval.json') == {'approved': True, 'review_sha256': digest}
    assert not (OUT / 'started.json').exists()
    path = PRIVATE / 'calibration-continuation.sqlite3'
    assert not path.exists()
    environment = preflight(review)
    save(OUT / 'started.json', {'review_sha256': digest, 'models': 0})
    scope = Scope(review_sha256=digest)
    ref = content_digest(scope)
    req = RecipeMaterializationRequest(plan_id=GRANT, subject_digest=ref, recipe_digest=ref,
        environment_digest=ref, mapping_digest=ref, authorization_id=GRANT, definition_digests=[ref], seed=0)
    result = {'review_sha256': digest, 'passed': False, 'models': 0, 'cases': {}}
    with ReceiptStore(str(path)) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_skillsbench_prefix_reference_scope', ref, scope) == ref
        repo.approve_bundle(AssessmentAuthorization(authorization_id=GRANT, subject_digests=[ref],
            recipe_digests=[ref], environment_digests=[ref], allowed_destinations=['local'],
            remote_disclosure=False, expires_at=datetime.fromisoformat(review['expires_at']),
            limits=AssessmentLimits(max_operations=5, max_model_turns=0, max_elapsed_seconds=275)),
            {ref: scope.model_dump(mode='json')})
        executor = ContainerExecutor(environment)

        def authorize():
            repo.authorize(req)
            preflight(review)
            return digest

        try:
            for case in CASES:
                invocation = context(case, authorize)
                spec = invocation.spec
                operation = invocation.attempt_id
                _, name = executor.command(invocation)
                assert runner['container_absent'](environment, name)
                repo.reserve(req, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=55), stage=case)
                started, clock = utc_now(), time.monotonic()
                facts, error = None, None
                try:
                    try:
                        raw = await executor.execute(invocation)
                    finally:
                        await executor.close()
                        assert runner['container_absent'](environment, name), 'owned container cleanup unverified'
                    assert raw.status.value == 'success', raw.error_type or 'contained calibration failed'
                    diagnostic = checked_failure(case, raw.output)
                    if diagnostic:
                        result['protected_diagnostic'] = diagnostic
                        raise RuntimeError('protected stage failed')
                    try:
                        facts = classify(case, raw.output)
                    except AssertionError:
                        result['unexpected_observation'] = raw.output
                        raise
                    facts['cleanup_confirmed'] = True
                    result['cases'][case] = facts
                except Exception as exc:
                    error = type(exc).__name__
                    raise
                finally:
                    elapsed = time.monotonic() - clock
                    receipt = ExecutionReceipt(decision_id=operation, action_id=operation, capability=spec.capability,
                        executor_id=spec.id, executor_kind=spec.kind, status='success' if facts else 'failed',
                        started_at=started, ended_at=utc_now(), estimated=spec.estimate,
                        actual_resources=ResourceVector(latency_ms=elapsed * 1000),
                        execution_success=facts is not None, error_type=error,
                        metadata={'review_sha256': digest, 'observation': facts,
                                  'observed_resource_dimensions': ['latency_ms']})
                    store.save_receipt(receipt)
                    repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                    save(OUT / f'{case}-receipt.json', receipt.model_dump(mode='json'))
            result['passed'] = True
        except Exception as exc:
            result['error_type'] = type(exc).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            result['operations'] = len(ledger.operations)
            result['accounting_settled'] = all(row.elapsed_seconds is not None for row in ledger.operations)
            save(OUT / 'ledger.json', ledger.model_dump(mode='json'))
            save(OUT / 'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
    return result['passed'] and result['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.preflight:
        preflight(read(REVIEW))
        print(json.dumps({'review_sha256': sha(REVIEW), 'preflight_passed': True, 'executed': False}))
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
