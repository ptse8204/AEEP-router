"""Bind a fresh, unstarted Langfuse continuation to the measured port blocker."""

import json
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from run import HERE, OLD, PROJECT, REDIS, SUBNET, base, check_subnet


def write(name, value):
    with (HERE / name).open('x') as out:
        json.dump(value, out, indent=2)
        out.write('\n')


def main():
    prior_path = OLD / 'operation-review.json'
    prior = base.load(prior_path)
    old_result = OLD / 'service-execution/summary.json'
    stopped = base.load(old_result)
    if stopped['passed'] or stopped['cleanup_uncertain'] or stopped['accounting_uncertain']:
        raise RuntimeError('Unreconciled or completed prior attempt')
    counters = stopped['grant_counters']
    with sqlite3.connect(Path(prior['ledger']).as_uri() + '?mode=ro', uri=True) as conn:
        recorded = list(conn.execute(
            'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
            (prior['grant_authorization_id'],)).fetchone())
        if counters != recorded:
            raise RuntimeError('Original grant moved after the prior attempt')
    docker = [prior['docker'], '--config', prior['docker_config'], '--host', 'unix://' + prior['docker_socket']]

    def observed(*args):
        return subprocess.check_output([*docker, *args], timeout=10, text=True).strip()

    prior_project = prior['project']
    port_shape = ('{"state":{{json .State.Status}},"wanted":{{json .HostConfig.PortBindings}},'
                  '"realized":{{json .NetworkSettings.Ports}},'
                  '"networks":{{json .NetworkSettings.Networks}}}')
    web = json.loads(observed('inspect', '--format', port_shape, prior_project + '-web'))
    network = json.loads(observed('network', 'inspect', '--format', '{{json .Internal}}', prior_project + '-private'))
    declared = {'3000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(base.PORT)}]}
    if (web['state'] != 'exited' or web['wanted'] != declared or any(web['realized'].values())
            or set(web['networks']) != {prior_project + '-private'} or not network):
        raise RuntimeError('Retained read-only diagnosis differs')
    check_subnet(prior)
    write('diagnosis.json', {
        'docker_engine': observed('version', '--format', '{{.Server.Version}}'),
        'only_internal_bridge': True, 'requested_port_binding': declared,
        'retained_realized_bindings': web['realized'],
        'prior_health_failures': 20, 'prior_next_js_ready_signal': True,
        'source': 'https://github.com/moby/moby/discussions/53256',
        'supported_inference': 'Internal-only bridge has no default-gateway network for host port publication.',
        'current_readonly_inspect_is_post_stop': True,
        'upstream_ingestion_reverified': False, 'new_subnet_disjoint': True,
    })
    new_work = Path(prior['work']).with_name(PROJECT)
    assert not new_work.exists()
    profile = (OLD / 'cli.sb').read_text().replace(str(prior['work']), str(new_work))
    with (HERE / 'cli.sb').open('x') as out:
        out.write(profile)
    prepared = base.load(OLD / 'prepared.json')
    prepared['request']['plan_id'] = PROJECT
    prepared['old_counters'] = counters
    write('prepared.json', prepared)
    amendment = prior['amendment'] | {
        'amendment_id': PROJECT, 'previous_amendment_digest': base.content_digest(prior['amendment']),
        'limits': prior['amendment']['limits'] | {'max_operations': counters[0] + 65},
        'issued_at': datetime.now(UTC).isoformat(),
    }
    write('budget-amendment.json', amendment)
    assets = prior['service_assets'] | {str(path): base.sha(path) for path in (
        prior_path, old_result, OLD / 'stopped-web-diagnostic.json',
        *(HERE / name for name in ('run.py', 'relay.py', 'prepare.py', 'check.py', 'check-result.json',
                                    'diagnosis.json', 'cli.sb', 'prepared.json', 'budget-amendment.json')),
    )}
    review = prior | {
        'project': PROJECT, 'work': str(new_work), 'cli_profile': str(HERE / 'cli.sb'),
        'purpose': 'One private Langfuse repeat with a narrowly scoped localhost-to-container stdio carrier.',
        'original_review_sha256': base.sha(prior_path), 'counters_before': counters,
        'maximum_additional_operations': 65, 'maximum_operations': counters[0] + 65,
        'maximum_driver_commands': prior['maximum_driver_commands'] + 2,
        'storage': prior['storage'] | {'free_bytes_at_preparation': shutil.disk_usage(HERE).free},
        'amendment': amendment, 'service_assets': assets,
        'approval_reason': 'The previous exact runtime attempt is terminal. The operator requires approval for repeats.',
        'lifecycle': prior['lifecycle'] | {
            'port': 'Only the host-owned Python listener at 127.0.0.1:39067. Verify Docker published no port while web is running.',
            'internal_subnet': SUBNET, 'internal_redis_address': REDIS,
            'carrier': 'Existing Docker exec stdio to the owned immutable web container and its 127.0.0.1:3000 listener.',
            'carrier_limits': '20 health GETs, one exact minimized receipt POST, up to eight matching observations GETs, no redirects or replay. Credentials local to task and transient.',
            'cleanup': 'Stop the owned host relay and only the newly owned container processes. Retain prior and new Docker resources.',
        },
        'service_started': False,
    }
    assert all(base.sha(path) == digest for path, digest in assets.items())
    write('operation-review.json', review)
    print(base.sha(HERE / 'operation-review.json'))


if __name__ == '__main__':
    main()
