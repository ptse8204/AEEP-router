"""Observe the actual guest network boundary before attempting upstream imports."""

import json
import os
import socket
import sys
from pathlib import Path


def socket_boundary():
    import errno
    import stat

    assert not any(stat.S_ISSOCK(os.fstat(fd).st_mode) for fd in (0, 1, 2))
    assert all(not path.readlink().as_posix().startswith('socket:')
               for path in Path('/proc/self/fd').iterdir() if path.exists())
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX, socket.AF_NETLINK):
        try:
            with socket.socket(family, socket.SOCK_RAW if family == socket.AF_NETLINK else socket.SOCK_STREAM):
                raise RuntimeError('socket creation unexpectedly succeeded')
        except PermissionError as error:
            assert error.errno == errno.EPERM
    try:
        socket.socketpair()
        raise RuntimeError('socket pair creation unexpectedly succeeded')
    except PermissionError as error:
        assert error.errno == errno.EPERM
    ipv4 = Path('/proc/net/route').read_text().splitlines()
    assert ipv4 and ipv4[0].split()[0] == 'Iface'
    assert all(row.split()[0] == 'lo' for row in ipv4[1:] if row.strip())
    ipv6 = Path('/proc/net/ipv6_route').read_text().splitlines()
    assert all(row.split()[-1] == 'lo' for row in ipv6 if row.strip())
    return {'ipv4_ipv6_unix_netlink_denied': True, 'socketpair_denied': True,
            'inherited_sockets': 0, 'non_loopback_route_devices': 0}


def main():
    result = {'models': 0, 'generated_code_executed': False, 'stage': 'containment',
              'optimizer_imported': False, 'actual_graph_parser_passed': False}
    try:
        assert (os.geteuid(), os.getegid()) == (65534, 65534)
        assert not Path('/var/run/docker.sock').exists() and not os.access('/opt', os.W_OK)
        status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
        assert status['NoNewPrivs'].strip() == '1' and int(status['CapEff'], 16) == 0
        assert status['Seccomp'].strip() == '2'
        result['boundary'] = socket_boundary()
        assert sys.version_info[:3] == (3, 12, 16)

        result['stage'] = 'upstream_import'
        sys.path[:0] = ['/opt/aflow-dependencies', '/opt/aflow-source']
        from contextlib import redirect_stdout

        with redirect_stdout(sys.stderr):
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
