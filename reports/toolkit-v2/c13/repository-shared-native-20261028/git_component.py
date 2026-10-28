"""Read a pinned Debian archive as data; copy only Git's local command component."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import urllib.error
import urllib.request

URL = 'https://deb.debian.org/debian/pool/main/g/git/git_2.47.3-0+deb13u1_arm64.deb'
SIZE = 8665568
SHA256 = '8c6b1e96b226211260d7814472215a8a1ed38ee37400c421d454391c1807cb5a'
OBJDUMP = Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/llvm-objdump')
PARENT_TAG = 'aeep-toolkit-v2/repository-grader:py313-multifile-20261027'
DOCKERFILE = ('FROM ' + PARENT_TAG + '\n'
    'COPY --chmod=0555 git /usr/bin/git\n'
    'COPY templates/ /usr/share/git-core/templates/\n'
    'COPY copyright /usr/share/doc/aeep-local-git/copyright\n')
NEEDED = {'libc.so.6', 'libpcre2-8.so.0', 'libz.so.1'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def selected_files(data):
    selected, seen, expanded = {}, set(), 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
            name = str(path)
            assert name not in seen
            seen.add(name)
            expanded += member.size
            assert len(seen) <= 4000 and expanded <= 64 * 1024**2
            keep = (name in ('usr/bin/git', 'usr/share/doc/git/copyright')
                    or name.startswith('usr/share/git-core/templates/'))
            if not keep or member.isdir():
                continue
            assert member.isfile() and member.size <= 10 * 1024**2
            assert not member.mode & 0o7000
            target = ('git' if name == 'usr/bin/git' else 'copyright'
                if name == 'usr/share/doc/git/copyright' else
                'templates/' + name.removeprefix('usr/share/git-core/templates/'))
            selected[target] = {'data': archive.extractfile(member).read(), 'mode': member.mode & 0o777}
    assert 'git' in selected and 'copyright' in selected
    assert any(n.startswith('templates/') for n in selected)
    assert len(selected) <= 100 and sum(len(v['data']) for v in selected.values()) <= 12 * 1024**2
    return selected


def write_context(context, files):
    context.mkdir(mode=0o700, exist_ok=False)
    for name, item in files.items():
        path = context / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item['data'])
        path.chmod(item['mode'])
    # COPY preserves directory modes; make traversal independent of host umask.
    for path in context.rglob('*'):
        if path.is_dir():
            path.chmod(0o755)
    (context / 'git').chmod(0o555)
    (context / 'Dockerfile').write_text(DOCKERFILE)


def prepare(context, cache, metadata):
    """Called only after exact approval; never run the downloaded Linux binary."""
    assert hashlib.sha256(OBJDUMP.read_bytes()).hexdigest() == metadata['objdump_sha256']
    cache.mkdir(exist_ok=False)
    archive = cache / 'git.deb'
    requests = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for attempt in range(1, 3):
        try:
            request = urllib.request.Request(URL, headers={'User-Agent': 'AEEP-exact-Git-review/1'})
            with opener.open(request, timeout=30) as response:
                assert response.geturl() == URL and response.status == 200
                data = response.read(SIZE + 1)
            assert len(data) == SIZE and hashlib.sha256(data).hexdigest() == SHA256
            with archive.open('xb') as stream:
                stream.write(data)
            requests.append({'attempt': attempt, 'passed': True, 'bytes': len(data)})
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            requests.append({'attempt': attempt, 'passed': False, 'error_type': type(exc).__name__})
            if attempt == 2:
                raise
    # System ar reads package data; Debian maintainer scripts are never extracted
    # or run. The Git executable is only inspected as ELF data on this Mac.
    member_names = subprocess.check_output(['/usr/bin/ar', '-t', str(archive)], timeout=10).decode().splitlines()
    assert member_names == ['debian-binary', 'control.tar.xz', 'data.tar.xz']
    data_tar = subprocess.check_output(['/usr/bin/ar', '-p', str(archive), 'data.tar.xz'], timeout=10)
    files = selected_files(data_tar)
    assert hashlib.sha256(files['copyright']['data']).hexdigest() == metadata['copyright_sha256']
    write_context(context, files)
    elf = subprocess.check_output([str(OBJDUMP), '-f', '-p', str(context / 'git')], timeout=20).decode()
    assert 'elf64-littleaarch64' in elf
    needed = set(re.findall(r'^\s*NEEDED\s+(\S+)\s*$', elf, re.MULTILINE))
    assert needed == NEEDED, 'Unexpected binary closure; do not build or install speculative libraries'
    return {'package_url': URL, 'package_sha256': SHA256, 'package_bytes': SIZE,
        'requests': requests, 'needed_libraries': sorted(needed), 'elf_inspection': elf,
        'context_files': {str(p.relative_to(context)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in context.rglob('*') if p.is_file()},
        'linux_binary_executed_on_host': False, 'maintainer_scripts_executed': False,
        'source_binary_redistributed': False}
