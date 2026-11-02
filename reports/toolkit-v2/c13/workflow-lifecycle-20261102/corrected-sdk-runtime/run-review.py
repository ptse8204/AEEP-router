"""Current-wheel/Framework check. Inert until exact approval and all source gates."""
from __future__ import annotations
import argparse, asyncio, json, shutil, sqlite3, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
# This source is captured before approval; it cannot follow later checkout edits.
FROZEN = ROOT / '.aeep/stack-frozen-source-e363cfa5'
sys.path.insert(0, str(FROZEN / 'src'))
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import RuntimeInstallation, apply, digest, file_digest, snapshot

GATES = ('compileall','schemas','assessment-policy','ruff','mypy','pytest','coverage-tests',
         'coverage-json','coverage-report','critical-coverage','assessment-coverage',
         'toolkit-integration-fixtures','build')


def make_spec(review, name, argv, seconds):
    work = HERE / 'execution/owned-work' / name
    spec = ExecutorSpec(
        id='toolkit.current-sdk-' + name, capability='toolkit.upstream-engineering@1',
        description='Reviewed isolated current-package and workflow SDK engineering check',
        kind='command', side_effect='write',
        config={'argv':['/usr/bin/sandbox-exec','-f',str(HERE / (name + '.sb')),
                        str(Path(review['runtime']) / 'bin/python'),'-I','-B',*argv],
                'argv_literal':True,'inherit_env':False,'stdin_json':True,'cwd':str(work),
                'timeout_seconds':seconds,'max_output_bytes':1048576,'output':{'type':'json'},
                'env':{'PATH':'/usr/bin:/bin','HOME':str(work / 'home'),'TMPDIR':str(work / 'tmp'),
                       'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}})
    action = ActionRequest(capability=spec.capability, input={
        'review_sha256':review['identity'], 'installed_source':review['installed_source'],
        'canary_path':str(HERE / 'functional-check.py')})
    context = ExecutionContext(request=action,spec=spec,estimate=spec.estimate,
                               attempt=1,approved_side_effect=SideEffect.WRITE)
    return spec, context


def verify():
    review = json.loads((HERE / 'operation-review.json').read_text())
    for name, value in review['bound_files'].items():
        assert file_digest(ROOT / name) == value, name
    manifest = json.loads((HERE / 'source-snapshot.json').read_text())
    assert manifest['snapshot_path'] == str(FROZEN)
    assert verification_source_digest(FROZEN) == manifest['source_digest'] == review['checkout_source']
    for name, value in manifest['files'].items():
        assert file_digest(FROZEN / name) == value, name
    plan = RuntimeInstallation.model_validate_json((HERE / 'installation.json').read_bytes())
    assert digest(plan) == review['installation_digest']
    assert plan.destination == review['runtime'] and len(plan.wheels) == 64
    for wheel in plan.wheels:
        assert file_digest(Path(plan.wheelhouse) / wheel.filename) == wheel.sha256
    review['identity'] = file_digest(HERE / 'operation-review.json')
    make_spec(review,'framework',['functional-check.py'],90)
    make_spec(review,'package',['package-check.py'],30)
    gates_file = ROOT / review['verification_checks']
    ready = False
    if gates_file.exists():
        gates = json.loads(gates_file.read_bytes())
        ready = (gates['source_before'] == gates['source_after'] == review['checkout_source']
                 and tuple(row['name'] for row in gates['checks']) == GATES
                 and all(row['exit_code'] == 0 for row in gates['checks']))
    return review, plan, ready


async def run(review, plan):
    with (HERE / 'execution-started.json').open('x') as stream:
        json.dump({'review_sha256':review['identity'],'started_at':utc_now().isoformat()},stream)
    execution = HERE / 'execution'
    execution.mkdir(mode=0o700)
    clock = time.monotonic()
    result = {'passed':False,'review_sha256':review['identity'],'models':0,'cash_usd':0,
              'components':{},'all_stack_integrations_complete':False,
              'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED'}
    store = ReceiptStore(execution / 'outer-receipts.sqlite3')
    baseline = None
    try:
        began = time.monotonic()
        installed = apply(plan, digest(plan))
        assert apply(plan, digest(plan)) == installed
        (execution / 'installation.json').write_text(json.dumps(installed,indent=2)+'\n')
        baseline = snapshot(Path(plan.destination))
        result['components']['installation'] = {'passed':True,'idempotent':True,
                                                'wall_seconds':time.monotonic()-began}

        async def execute(name, filename, seconds, probe=False):
            work = execution / 'owned-work' / name
            if not work.exists():
                work.mkdir(parents=True,mode=0o700)
                for child in ('home','tmp'):
                    (work / child).mkdir(mode=0o700)
            assert snapshot(Path(plan.destination)) == baseline
            worker = work / filename
            with worker.open('xb') as stream:
                stream.write((HERE / filename).read_bytes())
            spec, context = make_spec(review,name,[str(worker)],seconds)
            if probe:
                spec.config['argv'].insert(spec.config['argv'].index('-I')+1,'-S')
            executor, began = CommandExecutor(), utc_now()
            try:
                raw = await (await executor.start(context)).task
            finally:
                await executor.close()
            receipt = ExecutionReceipt(
                decision_id='reviewed-' + name + ('-boundary' if probe else '-component'),
                action_id=context.request.action_id,capability=spec.capability,
                executor_id=spec.id,executor_kind=spec.kind,status=raw.status,
                started_at=began,ended_at=utc_now(),estimated=spec.estimate,
                actual_resources=raw.resources,accounting=raw.accounting,
                execution_success=raw.status.value=='success',error_type=raw.error_type,
                metadata={'review_sha256':review['identity'],'evidence_kind':'upstream_engineering',**raw.metadata})
            store.save_receipt(receipt)
            label = name + ('-boundary' if probe else '-component')
            (execution / (label+'-receipt.json')).write_text(receipt.model_dump_json(indent=2)+'\n')
            (execution / (label+'-process.json')).write_text(json.dumps({
                'stdout':(raw.stdout or '')[:8192],'stderr':(raw.stderr or '')[:8192]},indent=2)+'\n')
            if isinstance(raw.output,dict):
                (execution / (label+'-result.json')).write_text(json.dumps(raw.output,indent=2)+'\n')
            assert snapshot(Path(plan.destination)) == baseline
            return raw, receipt

        for name in ('framework','package'):
            raw, _ = await execute(name,'boundary-check.py',20,probe=True)
            okay = raw.status.value=='success' and isinstance(raw.output,dict) and raw.output.get('passed') is True
            result['components'][name+'-boundary'] = {'passed':okay}
            if not okay:
                raise ValueError('common boundary is unverified; stop all dispatch')
        # The boundary probes have no canonical engineering IDs. Each component
        # has its own fresh workspace/database; old Graph state is inaccessible.
        raw, receipt = await execute('framework','functional-check.py',90)
        okay = (receipt.execution_success is True and isinstance(raw.output,dict)
                and raw.output.get('operations')==5 and raw.output.get('models')==0
                and len(raw.output.get('checks',[]))==5
                and all(check.get('passed') is True for check in raw.output['checks']))
        result['components']['framework'] = {'passed':okay,'receipt_id':receipt.receipt_id}
        # Inspect only this owned engineering database, read-only. An unresolved
        # reservation stops independent dispatch rather than guessing zero usage.
        database = execution / 'owned-work/framework/canonical.sqlite3'
        assert database.is_file()
        with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
            rows = connection.execute('SELECT state FROM assessment_operations').fetchall()
        assert len(rows) <= 5 and all(row[0] == 'complete' for row in rows), 'uncertain SDK accounting'
        (execution / 'framework-accounting-audit.json').write_text(json.dumps({
            'operations':len(rows),'unresolved':0,'scope':'only the owned SDK engineering database'},indent=2)+'\n')
        # A terminal Framework failure does not replay it or block independent
        # package inspection. Boundary/runtime/accounting uncertainty still stops.
        raw, receipt = await execute('package','package-check.py',30)
        okay = (receipt.execution_success is True and isinstance(raw.output,dict)
                and raw.output.get('passed') is True and raw.output.get('source')==review['installed_source'])
        result['components']['package'] = {'passed':okay,'receipt_id':receipt.receipt_id}
    except BaseException as error:
        result['error_type'] = type(error).__name__
    finally:
        store.close()
        result['runtime_retained'] = Path(plan.destination).exists()
        result['runtime_unchanged'] = baseline is not None and snapshot(Path(plan.destination)) == baseline
        result['wall_seconds'] = time.monotonic()-clock
        result['passed'] = (not result.get('error_type') and result['runtime_unchanged']
                            and set(result['components'])=={'installation','framework-boundary','package-boundary','framework','package'}
                            and all(value['passed'] for value in result['components'].values()))
        (execution / 'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-approved')
    args = parser.parse_args()
    review, plan, ready = verify()
    if args.execute_approved is None:
        print(json.dumps({'review_sha256':review['identity'],'executed':False,'installed':False,
                          'all_source_checks_passed':ready,'spec_context_validated':True}))
        return
    assert args.execute_approved==review['identity'] and ready
    approval=json.loads((HERE / 'operator-approval.json').read_bytes())
    assert approval['approved'] is True and approval['review_sha256']==review['identity']
    assert shutil.disk_usage(ROOT).free > 50*1024**3 + review['disk_reservation_bytes']
    print(json.dumps(asyncio.run(run(review,plan))))


if __name__=='__main__':
    main()
