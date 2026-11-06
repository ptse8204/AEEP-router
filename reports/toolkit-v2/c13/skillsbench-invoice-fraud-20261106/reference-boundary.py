"""Verify local task execution has no ambient privileges or non-loopback devices."""
import os
from pathlib import Path


def check():
    assert (os.geteuid(), os.getegid()) == (65534, 65534)
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    assert status['NoNewPrivs'].strip() == '1' and int(status['CapEff'], 16) == 0
    route_table = Path('/proc/net/route').read_text().splitlines()
    assert route_table and route_table[0].split()[0] == 'Iface'
    assert all(row.split()[0] == 'lo' for row in route_table[1:])
    assert not Path('/var/run/docker.sock').exists()
    assert not os.access('/etc', os.W_OK) and os.access('/root', os.W_OK)


if __name__ == '__main__':
    check()
