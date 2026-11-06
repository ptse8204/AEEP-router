"""Repeat private Langfuse verification once, using the narrow Docker exec carrier."""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import sys
from pathlib import Path

from relay import HEALTH, Scope, docker_transport, listen

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
PROJECT = 'aeep-langfuse-loopback-20261105'
SUBNET = '172.31.248.0/27'
POOL = '172.31.248.0/28'
REDIS = '172.31.248.30'
OLD = REPORTS / 'langfuse-static-redis-20261105'
BASE = REPORTS / 'langfuse-threadpool-correction-20261104'
sys.path[:0] = [str(BASE), str(REPORTS / 'langfuse-host-sandbox-20261105')]
from heap_adaptation import apply as apply_heap  # noqa: E402

spec = importlib.util.spec_from_file_location('reviewed_langfuse_service', BASE / 'run-service.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
from aeep.telemetry import receipt_otlp_preview  # noqa: E402

adapt_namespace = base.corrected
base.HERE = HERE
base.PROJECT = PROJECT
adapt_namespace.__globals__['PROJECT'] = PROJECT


def adapt(config, work):
    result = apply_heap(adapt_namespace(config, work))
    network = result['networks']['private']
    assert network['internal'] is True and 'ipam' not in network
    network['ipam'] = {'config': [{'subnet': SUBNET, 'ip_range': POOL}]}
    redis = result['services']['redis']
    assert redis['networks'] == ['private']
    redis['networks'] = {'private': {'ipv4_address': REDIS}}
    for role in ('web', 'worker'):
        app = result['services'][role]
        assert app['networks'] == ['private'] and 'extra_hosts' not in app
        app['extra_hosts'] = {'redis': REDIS}
    return result


class Journey(base.Journey):
    carrier = None
    carrier_scope = None

    def poll(self, path, **options):
        if path == HEALTH:
            assert self.carrier is None and options.get('expected') is None and options.get('auth') is None
            observed = self.inspect([PROJECT + '-web'])[0]
            assert observed['status'] == 'running'
            target = observed['id']
            template = ('{"ports":{{json .NetworkSettings.Ports}},'
                        '"networks":{{json .NetworkSettings.Networks}}}')
            data = json.loads(self.command('active-private-port-check',
                self.docker('inspect', '--format', template, target)))
            assert set(data['networks']) == {PROJECT + '-private'}
            assert not data['networks'][PROJECT + '-private']['Gateway']
            assert not any((data['ports'] or {}).values())
            self.carrier_scope = Scope(docker_transport(self.docker(), target, self.env))
            self.carrier = listen(base.PORT, self.carrier_scope)
            self.carrier.__enter__()
        return super().poll(path, **options)

    def cli(self, name, workflow, scope, receipt_id, auth=None, reviewed=None, configuration='document-data'):
        if name == 'export-once':
            receipt = self.repo.store.get_receipt(receipt_id)
            payload = receipt_otlp_preview(receipt)['payload']
            span = payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
            for attribute in span['attributes']:
                if attribute['key'] == 'aeep.evidence.trust':
                    attribute['value'] = {'stringValue': 'canonical_store_receipt'}
            self.carrier_scope.permit(auth, payload, span['traceId'])
        return super().cli(name, workflow, scope, receipt_id, auth, reviewed, configuration)

    def stop_owned(self):
        try:
            if self.carrier is not None:
                self.carrier.__exit__(None, None, None)
                base.write(self.output / 'carrier-result.json', {
                    'stopped': True, 'forwarding_counts': self.carrier_scope.counts,
                    'only_owned_web_loopback': True, 'raw_requests_or_responses_retained': False,
                })
        finally:
            super().stop_owned()


def check_subnet(review):
    import subprocess

    cmd = [review['docker'], '--config', review['docker_config'],
           '--host', 'unix://' + review['docker_socket']]
    ids = subprocess.check_output([*cmd, 'network', 'ls', '-q'], timeout=10, text=True).splitlines()
    assigned = subprocess.check_output([*cmd, 'network', 'inspect', '--format',
                                        '{{json .IPAM.Config}}', *ids], timeout=10, text=True)
    candidate = ipaddress.ip_network(SUBNET)
    for raw in assigned.splitlines():
        for conf in json.loads(raw) or []:
            if 'Subnet' in conf and candidate.overlaps(ipaddress.ip_network(conf['Subnet'])):
                raise RuntimeError('Private carrier subnet overlaps a retained Docker network')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-approved')
    args = parser.parse_args()
    path = HERE / 'operation-review.json'
    review = base.load(path)
    identity = base.sha(path)
    base.validate(review)
    check_subnet(review)
    if args.execute_approved is None:
        print(json.dumps({'review_sha256': identity, 'execution': False, 'subnet_disjoint': True}))
        return
    approval = base.load(HERE / 'operator-approval.json')
    assert args.execute_approved == identity == approval['review_sha256'] and approval['approved'] is True
    assert review['project'] == PROJECT and not (HERE / 'service-started.json').exists()
    base.corrected = adapt
    base.Journey = Journey
    result = base.execute(review, identity)
    print(json.dumps(result))
    raise SystemExit(not result['passed'])


if __name__ == '__main__':
    main()
