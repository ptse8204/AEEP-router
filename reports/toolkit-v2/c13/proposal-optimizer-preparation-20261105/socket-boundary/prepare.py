"""Derive a socket-denying profile from the retained daemon's vendored defaults."""

import hashlib
import json
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'namespace-observation'
SERVER_VERSION = '29.7.2'
SERVER_REVISION = '6a43e3d'
DROP = frozenset("""
    accept accept4 bind connect getsockname getpeername getsockopt listen
    recv recvfrom recvmmsg recvmmsg_time64 recvmsg send sendmsg sendmmsg sendto
    setsockopt shutdown socket socketcall socketpair pidfd_getfd
    io_uring_setup io_uring_enter io_uring_register
""".split())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    return sha(Path(path).read_bytes())


def publish(path, raw):
    with path.open('xb') as out:
        out.write(raw)


def write_json(path, value):
    publish(path, (json.dumps(value, indent=2) + '\n').encode())


def fetch(url):
    with urllib.request.urlopen(url, timeout=12) as response:
        raw = response.read(100_001)
    assert len(raw) <= 100_000
    return raw


def subtract(profile):
    assert profile['defaultAction'] == 'SCMP_ACT_ERRNO' and profile.get('defaultErrnoRet', 1) == 1
    return {
        **profile,
        'syscalls': [
            {**rule, 'names': keep}
            for rule in profile['syscalls']
            if (keep := [name for name in rule['names'] if name not in DROP])
        ],
    }


def main():
    prior_path = PREVIOUS / 'operation-review.json'
    result_path = PREVIOUS / 'result.json'
    ledger_path = PREVIOUS / 'ledger.json'
    prior, result, ledger = (json.loads(path.read_bytes()) for path in (prior_path, result_path, ledger_path))
    assert digest(prior_path) == result['review_sha256']
    assert result['cleanup_verified'] and result['observed']['stage'] == 'containment'
    assert not result['observed']['optimizer_imported']
    assert result['observed']['boundary']['non_loopback_devices'] > 0
    assert len(ledger['operations']) == 1 and ledger['operations'][0]['elapsed_seconds'] is not None
    for path, expected in prior['assets'].items():
        assert digest(path) == expected

    commit_info = json.loads(fetch('https://api.github.com/repos/moby/moby/commits/' + SERVER_REVISION))
    revision = commit_info['sha']
    assert revision.startswith(SERVER_REVISION)
    url = ('https://raw.githubusercontent.com/moby/moby/' + revision
           + '/vendor/github.com/moby/profiles/seccomp/default.json')
    baseline = fetch(url)
    default = json.loads(baseline)
    profile = subtract(default)
    names = {name for rule in profile['syscalls'] for name in rule['names']}
    source_names = {name for rule in default['syscalls'] for name in rule['names']}
    assert not names & DROP and names == source_names - DROP and 'socket' in source_names
    path = HERE / 'seccomp.json'
    write_json(path, profile)
    write_json(HERE / 'profile-source.json', {
        'engine_version': SERVER_VERSION, 'engine_revision': revision, 'source_url': url,
        'default_profile_sha256': sha(baseline), 'derived_profile_sha256': digest(path),
        'removed_syscall_names': sorted(source_names & DROP),
        'license': 'Apache-2.0',
        'license_url': url.rsplit('/', 1)[0] + '/LICENSE',
        'license_sha256': digest(HERE / 'MOBY-LICENSE'),
        'remaining_rules_have_only_source_entries': True,
    })
    source = (PREVIOUS / 'check.py').read_text()
    start = source.index('def network_observation():')
    end = source.index('\n\ndef main():', start)
    probe = """def socket_boundary():
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
"""
    source = source[:start] + probe + source[end:]
    source = source.replace("        result['boundary'] = network_observation()\n"
                            "        assert not result['boundary']['non_loopback_devices']\n"
                            "        assert result['boundary']['loopback_verified']",
                            "        assert status['Seccomp'].strip() == '2'\n"
                            "        result['boundary'] = socket_boundary()")
    start = source.index('        import numpy')
    end = source.index("    except Exception as error:", start)
    source = source[:start] + "        from contextlib import redirect_stdout\n\n        with redirect_stdout(sys.stderr):\n" + ''.join(
        '    ' + line if line.strip() else line for line in source[start:end].splitlines(keepends=True)
    ) + source[end:]
    compile(source, str(HERE / 'check.py'), 'exec')
    publish(HERE / 'check.py', source.encode())

    name = 'aeep-aflow-socket-boundary-20261106'
    argv = [arg.replace(prior['container_name'], name)
            .replace(str(PREVIOUS / 'check.py'), str(HERE / 'check.py')) for arg in prior['argv']]
    at = argv.index('--security-opt=no-new-privileges') + 1
    argv.insert(at, '--security-opt=seccomp=' + str(path))
    runner = (PREVIOUS / 'run.py').read_text().replace(
        'aflow-runtime-namespace-observation-20261106', 'aflow-runtime-socket-boundary-20261106'
    ).replace('aflow_runtime_namespace_observation', 'aflow_runtime_socket_boundary')
    line = "    assert not (HERE/'started.json').exists()"
    assert line in runner
    runner = runner.replace(line, line + """
    version = subprocess.check_output([*review['docker'], 'version', '--format',
        '{{.Server.Version}} {{.Server.GitCommit}}'], text=True, env=review['environment'], timeout=10)
    assert version.strip().split() == [review['engine_version'], review['engine_revision_short']]
""".rstrip())
    compile(runner, str(HERE / 'run.py'), 'exec')
    publish(HERE / 'run.py', runner.encode())
    assets = {**prior['assets'], **{str(p): digest(p) for p in (
        prior_path, result_path, ledger_path, HERE / 'profile-source.json', path,
        HERE / 'check.py', HERE / 'run.py', HERE / 'MOBY-LICENSE', Path(__file__),
    )}}
    prior.update(
        scope='One exact AFlow repeat with a default-deny socket profile and the same Docker network isolation.',
        argv=argv, container_name=name, assets=assets, previous_review_sha256=digest(prior_path),
        engine_version=SERVER_VERSION, engine_revision_short=SERVER_REVISION,
        expires_at=(datetime.now(UTC) + timedelta(days=2)).isoformat(),
    )
    review = HERE / 'operation-review.json'
    write_json(review, prior)
    print(digest(review))


if __name__ == '__main__':
    main()
