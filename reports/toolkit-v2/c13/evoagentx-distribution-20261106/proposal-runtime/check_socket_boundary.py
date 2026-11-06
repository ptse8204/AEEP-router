import os
import socket
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
        socket.socketpair(socket.AF_INET)
        raise RuntimeError('non-Unix socketpair unexpectedly succeeded')
    except PermissionError as error:
        assert error.errno == errno.EPERM
    left, right = socket.socketpair(socket.AF_UNIX)
    with left, right:
        assert left.send(b'aeep') == 4 and right.recv(4) == b'aeep'
    ipv4 = Path('/proc/net/route').read_text().splitlines()
    assert ipv4 and ipv4[0].split()[0] == 'Iface'
    assert all(row.split()[0] == 'lo' for row in ipv4[1:] if row.strip())
    ipv6 = Path('/proc/net/ipv6_route').read_text().splitlines()
    assert all(row.split()[-1] == 'lo' for row in ipv6 if row.strip())
    return {'ipv4_ipv6_unix_netlink_denied': True, 'non_unix_socketpair_denied': True, 'local_unix_pair_verified': True,
            'inherited_sockets': 0, 'non_loopback_route_devices': 0}

