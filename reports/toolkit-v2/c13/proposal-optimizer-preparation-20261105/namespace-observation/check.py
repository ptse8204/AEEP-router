"""Observe the actual guest network boundary before attempting upstream imports."""

import json
import os
import socket
import sys
from pathlib import Path


def network_observation():
    indexed = {name for _, name in socket.if_nameindex()}
    sysfs = {item.name for item in Path('/sys/class/net').iterdir()}
    ipv4 = Path('/proc/net/route').read_text().splitlines()
    assert ipv4 and ipv4[0].split()[0] == 'Iface'
    ipv4_devices = {row.split()[0] for row in ipv4[1:] if row.strip()}
    ipv6 = Path('/proc/net/ipv6_route').read_text().splitlines()
    ipv6_devices = {row.split()[-1] for row in ipv6 if row.strip()}
    unexpected = (indexed | sysfs | ipv4_devices | ipv6_devices) - {'lo'}
    return {
        'interface_index_count': len(indexed), 'sysfs_interface_count': len(sysfs),
        'ipv4_route_devices': len(ipv4_devices), 'ipv6_route_devices': len(ipv6_devices),
        'non_loopback_devices': len(unexpected), 'loopback_verified': 'lo' in sysfs,
    }


def main():
    result = {'models': 0, 'generated_code_executed': False, 'stage': 'containment',
              'optimizer_imported': False, 'actual_graph_parser_passed': False}
    try:
        assert (os.geteuid(), os.getegid()) == (65534, 65534)
        assert not Path('/var/run/docker.sock').exists() and not os.access('/opt', os.W_OK)
        status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
        assert status['NoNewPrivs'].strip() == '1' and int(status['CapEff'], 16) == 0
        result['boundary'] = network_observation()
        assert not result['boundary']['non_loopback_devices']
        assert result['boundary']['loopback_verified']
        assert sys.version_info[:3] == (3, 12, 16)

        result['stage'] = 'upstream_import'
        sys.path[:0] = ['/opt/aflow-dependencies', '/opt/aflow-source']
        import numpy
        import pandas
        from scripts.optimizer import GraphOptimize, Optimizer
        from scripts.optimizer_utils.graph_utils import GraphUtils

        assert numpy.__version__ == '2.0.2' and pandas.__version__ == '2.2.3'
        assert Path(sys.modules[Optimizer.__module__].__file__).parent == Path('/opt/aflow-source/scripts')
        result['optimizer_imported'] = True
        result['stage'] = 'upstream_graph_parser'
        fixture = 'class Workflow:\n    async def __call__(self):\n        return 1\n'
        assert GraphUtils('/tmp/reviewed-graph').extract_solve_graph(fixture) == [fixture]
        assert set(GraphOptimize.model_fields) == {'modification', 'graph', 'prompt'}
        result.update(stage='complete', actual_graph_parser_passed=True)
    except Exception as error:
        result['error_type'] = type(error).__name__
        if isinstance(error, OSError):
            result['errno'] = error.errno
        if isinstance(error, ImportError) and error.name and error.name.replace('.', '').replace('_', '').isalnum():
            result['import_name'] = error.name
    print(json.dumps(result))


if __name__ == '__main__':
    main()
