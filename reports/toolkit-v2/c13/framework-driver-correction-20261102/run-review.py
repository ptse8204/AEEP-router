"""One Framework-only continuation; immutable retained SDK and narrow boundary."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, shutil, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FROZEN = ROOT / '.aeep/stack-frozen-source-443b90a7'
sys.path.insert(0, str(FROZEN / 'src'))
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest, snapshot


def build_spec(review, working, worker, *, interpreter=None):
    return ExecutorSpec(
        id='toolkit.framework-driver-continuation', capability='toolkit.upstream-engineering@1',
        description='Reviewed Agent Framework numeric composition check in an owned isolated workspace',
        kind='command', side_effect='write',
        config={'argv':['/usr/bin/sandbox-exec', '-f', str(ROOT / review['profile']),
                        str(interpreter or Path(review['runtime']) / 'bin/python'), '-I', '-B', str(worker)],
                'argv_literal':True, 'inherit_env':False, 'stdin_json':True,
                'cwd':str(working), 'timeout_seconds':90, 'max_output_bytes':1048576,
                'output':{'type':'json'}, 'env':{'PATH':'/usr/bin:/bin',
                'HOME':str(working / 'home'), 'TMPDIR':str(working / 'tmp'),
                'PYTHONNOUSERSITE':'1', 'PYTHONDONTWRITEBYTECODE':'1', 'LC_ALL':'C'}})


def context_for(spec, identity, review):
    action = ActionRequest(capability=spec.capability, input={
        'review_sha256':identity, 'installed_source':review['installed_source'],
        'canary_path':str(ROOT / review['worker'])})
    return ExecutionContext(request=action, spec=spec, estimate=spec.estimate,
                            attempt=1, approved_side_effect=SideEffect.WRITE)


def verify():
    review = json.loads((HERE / 'operation-review.json').read_text())
    for name, value in review['bound_files'].items():
        assert file_digest(ROOT / name) == value, name
    assert verification_source_digest(FROZEN) == review['checkout_source']
    assert snapshot(Path(review['runtime'])) == review['runtime_snapshot']
    identity = file_digest(HERE / 'operation-review.json')
    working = Path(review['workspace'])
    assert working.parent.is_dir() and not working.exists()
    spec = build_spec(review, working, working / 'functional-check.py')
    context_for(spec, identity, review)
    return review, identity


async def execute(review, identity):
    with (HERE / 'execution-started.json').open('x') as stream:
        json.dump({'review_sha256':identity, 'attempt':1}, stream)
    working = Path(review['workspace'])
    working.mkdir(mode=0o700)
    for name in ('home', 'tmp'):
        (working / name).mkdir(mode=0o700)
    worker = working / 'functional-check.py'
    worker.write_bytes((ROOT / review['worker']).read_bytes())
    assert file_digest(worker) == review['worker_sha256']
    spec = build_spec(review, working, worker)
    context = context_for(spec, identity, review)
    executor, raw, started = CommandExecutor(), None, utc_now()
    clock = time.monotonic()
    result = {'passed':False, 'review_sha256':identity, 'models':0, 'cash_usd':0,
              'runtime_retained':True, 'owned_work':str(working)}
    try:
        raw = await (await executor.start(context)).task
        receipt = ExecutionReceipt(
            decision_id='framework-driver-continuation', action_id=context.request.action_id,
            capability=spec.capability, executor_id=spec.id, executor_kind=spec.kind,
            status=raw.status, started_at=started, ended_at=utc_now(), estimated=spec.estimate,
            actual_resources=raw.resources, accounting=raw.accounting,
            execution_success=raw.status.value == 'success', error_type=raw.error_type,
            metadata={'review_sha256':identity, 'evidence_kind':'upstream_engineering', **raw.metadata})
        store = ReceiptStore(HERE / 'outer-receipts.sqlite3')
        try:
            store.save_receipt(receipt)
        finally:
            store.close()
        (HERE / 'receipt.json').write_text(receipt.model_dump_json(indent=2) + '\n')
        (HERE / 'process.json').write_text(json.dumps({
            'stdout':(raw.stdout or '')[:8192], 'stderr':(raw.stderr or '')[:8192]}, indent=2) + '\n')
        result['receipt_id'] = receipt.receipt_id
        if isinstance(raw.output, dict):
            (HERE / 'result.json').write_text(json.dumps(raw.output, indent=2) + '\n')
            result['passed'] = (receipt.execution_success is True and raw.output.get('operations') == 5
                and raw.output.get('models') == 0 and len(raw.output.get('checks', [])) == 5
                and all(check.get('passed') is True for check in raw.output['checks']))
    except BaseException as error:
        result['error_type'] = type(error).__name__
    finally:
        await executor.close()
        result['wall_seconds'] = time.monotonic() - clock
        result['runtime_unchanged'] = snapshot(Path(review['runtime'])) == review['runtime_snapshot']
        result['passed'] = result['passed'] and result['runtime_unchanged']
        (HERE / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-approved')
    args = parser.parse_args()
    review, identity = verify()
    if args.execute_approved is None:
        print(json.dumps({'review_sha256':identity, 'executed':False, 'spec_validated':True}))
        return
    assert args.execute_approved == identity
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] is True and approval['review_sha256'] == identity
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 32 * 1024**2
    print(json.dumps(asyncio.run(execute(review, identity))))


if __name__ == '__main__':
    main()
