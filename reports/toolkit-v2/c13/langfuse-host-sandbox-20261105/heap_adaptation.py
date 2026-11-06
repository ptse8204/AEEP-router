"""Use the measured startup failure to adjust only the two Node service caps."""

PROJECT = 'aeep-langfuse-web-heap-20261104'
NODE_SERVICES = ('web', 'worker')
NODE_HEAP_MIB = 1024
NODE_CONTAINER_MIB = 1536


def apply(compose):
    for name in NODE_SERVICES:
        service = compose['services'][name]
        assert service['pids_limit'] == 256
        assert service['mem_limit'] == service['memswap_limit'] == '1024m'
        assert service['environment']['NODE_OPTIONS'] == '--max-old-space-size=640'
        service['mem_limit'] = service['memswap_limit'] = f'{NODE_CONTAINER_MIB}m'
        service['environment']['NODE_OPTIONS'] = f'--max-old-space-size={NODE_HEAP_MIB}'
    return compose
