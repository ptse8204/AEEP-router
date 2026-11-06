"""Bind Redis on the owned internal network without relying on its DNS alias."""

PROJECT = 'aeep-langfuse-static-redis-20261105'
SUBNET = '172.31.249.0/27'
DYNAMIC_RANGE = '172.31.249.0/28'
REDIS_IP = '172.31.249.30'


def apply(compose):
    network = compose['networks']['private']
    assert network['internal'] is True and 'ipam' not in network
    network['ipam'] = {'config': [{'subnet': SUBNET, 'ip_range': DYNAMIC_RANGE}]}
    redis = compose['services']['redis']
    assert redis['networks'] == ['private']
    redis['networks'] = {'private': {'ipv4_address': REDIS_IP}}
    for name in ('web', 'worker'):
        service = compose['services'][name]
        assert service['networks'] == ['private'] and 'extra_hosts' not in service
        service['extra_hosts'] = {'redis': REDIS_IP}
    return compose
