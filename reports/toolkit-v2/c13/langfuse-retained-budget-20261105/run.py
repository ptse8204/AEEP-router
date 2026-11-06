"""Continue only the stopped private Langfuse service and its unstarted export."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from security import decode, normalize_mounts

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'langfuse-loopback-carrier-20261105'
sys.path.insert(1, str(PRIOR))
spec = importlib.util.spec_from_file_location('reviewed_langfuse_carrier', PRIOR / 'run.py')
carrier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(carrier)
base = carrier.base
PROJECT = carrier.PROJECT
DATASTORES = ('postgres', 'clickhouse', 'redis', 'minio')
LIVE = (*DATASTORES, 'web', 'worker')
BIND_TEMPLATE = '{{json .HostConfig}} {{json .Mounts}} {{json .NetworkSettings.Networks}} {{json .Config.User}}'
STATE_TEMPLATE = '{{json .Id}} {{json .State.Status}} {{json .State.ExitCode}} {{json .Config.Labels}}'
HEALTH_TEMPLATE = '{{json .Id}} {{json .State.Status}} {{json .State.Health.Status}}'


def allowed_binds(work):
    return {'clickhouse': {base.POOL_TARGET: (str(work / 'clickhouse-pools.xml'), False)},
            'minio-bucket': {'/run/mc': (str(work / 'mc'), True)}}


def objects(review, *args):
    return [review['docker'], '--config', review['docker_config'],
            '--host', 'unix://' + review['docker_socket'], *args]


def safe_read(review, *args):
    return subprocess.check_output(objects(review, *args), text=True, timeout=12)


def export_count(connection, grant_id):
    return connection.execute(
        "SELECT count(*) FROM assessment_operations operation JOIN assessment_records started "
        "ON started.kind='operation_start' AND started.id=operation.id "
        "WHERE operation.grant_id=? AND json_extract(started.payload_json, '$.stage')='workflow_receipt_export'",
        (grant_id,),
    ).fetchone()[0]


def checks(review):
    base.validate(review)
    before = base.load(PRIOR / 'service-execution/summary.json')
    closed = base.load(PRIOR / 'service-execution/stop-verdict.json')
    assert not before['cleanup_uncertain'] and not before['accounting_uncertain'] and not before['passed']
    assert review['counters_before'] == before['grant_counters'] and review['containers'] == closed['owned_container_ids']
    assert closed['passed'] and not closed['containers_removed']
    assert base.snapshot(Path(review['installed_runtime'])) == review['installed_runtime_snapshot']
    with sqlite3.connect(Path(review['ledger']).as_uri() + '?mode=ro', uri=True) as db:
        grant = db.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
                           (review['grant_authorization_id'],)).fetchone()
        assert list(grant) == review['counters_before']
        assert not db.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",
                              (review['grant_authorization_id'],)).fetchone()
        assert export_count(db, review['grant_authorization_id']) == 0
    ids = [review['containers'][service] for service in base.SERVICES]
    for service, row in zip(base.SERVICES, safe_read(review, 'inspect', '--format', STATE_TEMPLATE, *ids).splitlines(), strict=True):
        ident, state, code, labels = tuple(decode(row))
        assert ident == review['containers'][service] and re.fullmatch('[0-9a-f]{64}', ident)
        assert state == 'exited' and labels[base.LABEL] == PROJECT and labels['com.docker.compose.service'] == service
        if service not in LIVE:
            assert code == 0
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', base.PORT))
    return check_permissions(review, ids)


def check_permissions(review, ids):
    """Reuse all prior permission checks after normalizing the two known mounts."""
    text = safe_read(review, 'inspect', '--format', BIND_TEMPLATE, *ids)
    translated, observed = normalize_mounts(text, base.SERVICES, allowed_binds(Path(review['work'])))
    network = safe_read(review, 'network', 'inspect', PROJECT+'-private', '--format',
                        '{{json .Internal}} {{json .Labels}}')
    internal, labels = tuple(decode(network))
    assert internal is True and labels[base.LABEL] == PROJECT

    class LocalObservation:
        work = Path(review['work'])
        output = HERE

        def docker(self, *args):
            return args

        def command(self, name, _argv):
            assert name in {'permission-inspection', 'network-inspection'}
            return translated if name == 'permission-inspection' else network

    def confirm(_path, verdict):
        assert verdict['passed'] is True

    write = base.write
    try:
        base.write = confirm
        base.Journey.inspect_security(LocalObservation())
    finally:
        base.write = write
    return observed


class Journey(carrier.Journey):
    def __init__(self, review, repository, request, identity):
        super().__init__(review, repository, request, identity)
        self.owned = review['containers'].copy()
        self.started_ids = set()

    def command(self, name, *args, **kwargs):
        text = super().command(name, *args, **kwargs)
        if name == 'permission-inspection':
            text, observed = normalize_mounts(text, base.SERVICES, allowed_binds(self.work))
            base.write(self.output/f'mounts-{self.number}.json', observed)
        return text

    def start(self, *services):
        self.started_ids.update(self.owned[s] for s in services)
        self.command('start-retained-' + services[0], self.docker('start', *(self.owned[s] for s in services)))

    def wait_datastores(self):
        expected = [self.owned[s] for s in DATASTORES]
        for _ in range(8):
            observed = [tuple(decode(row)) for row in self.command(
                'datastore-health', self.docker('inspect', '--format', HEALTH_TEMPLATE, *expected), 8).splitlines()]
            assert [row[0] for row in observed] == expected
            assert all(state == 'running' and health in ('starting', 'healthy') for _, state, health in observed)
            if all(health == 'healthy' for _, _, health in observed):
                return
            time.sleep(3)
        raise RuntimeError('RetainedDatastoresNotHealthy')

    def stop_owned(self):
        try:
            if self.carrier is not None:
                self.carrier.__exit__(None, None, None)
                base.write(self.output/'carrier-result.json', {'stopped': True,
                    'forwarding_counts': self.carrier_scope.counts,
                    'raw_requests_or_responses_retained': False})
        finally:
            names = [PROJECT+'-'+name for name in base.SERVICES]
            current = self.inspect(names, cleanup=True)
            live = [row['id'] for row in current if row['id'] in self.started_ids and row['status'] == 'running']
            assert not any(row['status'] == 'running' and row['id'] not in self.started_ids for row in current)
            if live:
                self.command('stop-retained', self.docker('stop','--time','15',*live),60,cleanup=True)
            after = self.inspect(names, cleanup=True)
            assert all(row['status'] == 'exited' for row in after)
            base.write(self.output/'stop-verdict.json',{'passed': True,
                'containers': self.owned, 'all_retained_stopped': True, 'resources_deleted': False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-approved')
    args = parser.parse_args()
    path = HERE/'operation-review.json'
    review = base.load(path)
    identity = base.sha(path)
    assert not (HERE/'service-started.json').exists()
    observed = checks(review)
    if args.execute_approved is None:
        print(json.dumps({'passed':True,'execution':False,'review_sha256':identity,'mounts':observed}))
        return
    approval = base.load(HERE/'operator-approval.json')
    assert args.execute_approved == identity == approval['review_sha256'] and approval['approved'] is True
    base.HERE = HERE
    execute(review, identity)


def execute(review, identity):
    out = HERE/'service-execution'
    out.mkdir(mode=0o700)
    with (HERE/'service-started.json').open('x') as stream:
        json.dump({'review_sha256':identity},stream)
    prepared = base.load(PRIOR/'prepared.json')
    original = base.RecipeMaterializationRequest.model_validate(prepared['request'])
    request = original.model_copy(update={'plan_id':review['continuation_plan_id']})
    with base.ReceiptStore(review['ledger']) as store:
        repo = base.AssessmentRepository(store)
        journey = Journey(review, repo, request, identity)
        assert journey.counters() == review['counters_before']
        repo.approve_budget_amendment(base.AssessmentBudgetAmendment.model_validate(review['amendment']))
        outer = request.model_copy(update={'plan_id':request.plan_id+':overhead'})
        cleanup = request.model_copy(update={'plan_id':request.plan_id+':cleanup'})
        outer_id, cleanup_id = outer.plan_id+':interval', cleanup.plan_id+':interval'
        repo.reserve(outer,outer_id,base.AssessmentLimits(max_operations=1,max_elapsed_seconds=300),stage='langfuse_driver_overhead')
        repo.reserve(cleanup,cleanup_id,base.AssessmentLimits(max_operations=1,max_elapsed_seconds=650),stage='langfuse_owned_cleanup')
        phase = 'identity and permissions'
        started = time.perf_counter()
        result = {'passed':False,'comparisons':'PAUSED','models':0,'health_verified':False,
                  'transport_accepted':False,'ingestion_verified':False,'disabled_export_verified':False,
                  'cleanup_uncertain':False,'accounting_uncertain':False}
        try:
            rows = journey.inspect([PROJECT+'-'+name for name in base.SERVICES])
            assert all(row['status'] == 'exited' for row in rows)
            journey.inspect_security()
            phase = 'retained service startup'
            journey.start(*DATASTORES)
            journey.wait_datastores()
            journey.start('web')
            assert journey.poll(carrier.HEALTH,attempts=20)
            result['health_verified'] = True
            journey.start('worker')
            rows = journey.inspect([PROJECT+'-'+name for name in base.SERVICES])
            assert all(row['status'] == ('running' if row['service'] in LIVE else 'exited') for row in rows)
            phase = 'active permissions and egress'
            journey.inspect_security()
            probe = (base.INPUT/'network-probe.js').read_text()
            network = json.loads(journey.command('egress-probe',journey.docker('exec',journey.owned['worker'],'node','-e',probe),15))
            assert network.get('external_connect_denied') is True
            base.write(out/'network-probe.json',network)
            phase = 'exact receipt preview'
            receipt_id = prepared['source_receipt_id']
            facts = journey.cli('export-preview','enabled-workflow.json','enabled-accounting.json',receipt_id)
            assert facts['enabled'] and facts['source_receipt_sha256'] == prepared['source_receipt_sha256']
            # Only the existing task-owned local project keys are consumed.
            local = base.load(journey.work/'compose-tmpfs.json')['services']['web']['environment']
            auth = 'Basic '+base64.b64encode((local['LANGFUSE_INIT_PROJECT_PUBLIC_KEY']+':'+local['LANGFUSE_INIT_PROJECT_SECRET_KEY']).encode()).decode()
            phase = 'one local receipt export'
            exported = journey.cli('export-once','enabled-workflow.json','enabled-accounting.json',receipt_id,auth,facts['review_sha256'])
            assert exported['transport_accepted'] and not exported['ingestion_verified']
            result['transport_accepted'] = True
            phase = 'exact trace readback'
            result['ingestion_verified'] = journey.poll('/api/public/v2/observations',expected=exported,auth=auth)
            assert result['ingestion_verified']
            result.update(trace_id=exported['trace_id'],span_id=exported['span_id'],
                          source_receipt_sha256=exported['source_receipt_sha256'],export_record_ref=exported['record_ref'])
            phase = 'disabled export'
            before = export_count(store._connection, request.authorization_id)
            disabled_preview = journey.cli('disabled-preview','disabled-workflow.json','disabled-accounting.json',receipt_id,configuration='software-engineering')
            disabled = journey.cli('disabled-check','disabled-workflow.json','disabled-accounting.json',receipt_id,
                                   reviewed=disabled_preview['review_sha256'],configuration='software-engineering')
            after = export_count(store._connection, request.authorization_id)
            assert disabled['status']=='disabled' and not disabled['export_performed'] and before == after == 1
            assert journey.carrier_scope.counts['export'] == 1
            result.update(disabled_export_verified=True,disabled_transport_charge_delta=after-before,passed=True)
        except BaseException as error:
            result.update(error_type=type(error).__name__,stopped_phase=phase)
        finally:
            try:
                journey.stop_owned()
            except BaseException as error:
                result.update(cleanup_uncertain=True,cleanup_error_type=type(error).__name__)
            try:
                elapsed = max(0.,time.perf_counter()-started-journey.child_seconds)
                repo.finish_operation(outer_id,elapsed_seconds=elapsed,resources=base.ResourceVector(latency_ms=elapsed*1000))
                if not result['cleanup_uncertain']:
                    repo.finish_operation(cleanup_id,elapsed_seconds=journey.cleanup_seconds,resources=base.ResourceVector(latency_ms=journey.cleanup_seconds*1000))
                result['accounting_uncertain'] = bool(store._connection.execute(
                    "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone())
                for label, name in (('commands',request.plan_id+':driver-commands'),('workflow',request.plan_id),
                                    ('overhead',outer.plan_id),('cleanup',cleanup.plan_id)):
                    base.write(out/(label+'-ledger.json'),repo.operation_ledger(name).model_dump(mode='json'))
                result['grant_counters'] = journey.counters()
                assert result['grant_counters'][0] <= review['maximum_operations'] and result['grant_counters'][1] == 0
            except BaseException as error:
                result.update(accounting_uncertain=True,accounting_error_type=type(error).__name__)
            result['free_bytes_after'] = shutil.disk_usage(base.ROOT).free
            result['passed'] = result['passed'] and not result['accounting_uncertain'] and not result['cleanup_uncertain']
            base.write(out/'summary.json',result)
    print(json.dumps(result))
    raise SystemExit(not result['passed'])


if __name__ == '__main__':
    main()
