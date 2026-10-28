"""Exercise the selection boundary using tiny authored tar fixtures, not Git."""
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile

from git_component import DOCKERFILE, selected_files, write_context


def bundle(problem=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:xz') as archive:
        files = [('usr/bin/git', b'AUTHORED NONEXECUTABLE FIXTURE'),
            ('usr/share/doc/git/copyright', b'authored license'),
            ('usr/share/git-core/templates/info/exclude', b'authored template'),
            ('usr/lib/git-core/git-remote-http', b'NEVER SELECT THIS')]
        if problem == 'escape':
            files.append(('../escape', b'no'))
        if problem == 'duplicate':
            files.append(files[0])
        for name, data in files:
            item = tarfile.TarInfo('./' + name)
            item.size = len(data)
            item.mode = 0o4755 if problem == 'setuid' and name == 'usr/bin/git' else 0o644
            if problem == 'symlink' and name == 'usr/bin/git':
                item.type = tarfile.SYMTYPE
                item.linkname = '/etc/passwd'
            archive.addfile(item, io.BytesIO(data))
    return stream.getvalue()


def main():
    good = selected_files(bundle())
    assert set(good) == {'git', 'copyright', 'templates/info/exclude'}
    for problem in ('escape', 'duplicate', 'setuid', 'symlink'):
        try:
            selected_files(bundle(problem))
        except AssertionError:
            pass
        else:
            raise AssertionError(problem + ' accepted')
    assert len(DOCKERFILE.splitlines()) == 4
    assert [line.split()[0] for line in DOCKERFILE.splitlines()] == ['FROM', 'COPY', 'COPY', 'COPY']
    with tempfile.TemporaryDirectory(prefix='aeep-authored-component-') as temp:
        context = Path(temp) / 'context'
        previous = os.umask(0o077)
        try:
            write_context(context, good)
        finally:
            os.umask(previous)
        assert stat.S_IMODE(context.stat().st_mode) == 0o700
        assert stat.S_IMODE((context / 'git').stat().st_mode) == 0o555
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o755 for p in context.rglob('*') if p.is_dir())
        assert (context / 'templates/info/exclude').read_bytes() == good['templates/info/exclude']['data']
    assert not Path(temp).exists()
    result = {'passed': True, 'authored_fixture_only': True,
        'checks': ['selected_component_only', 'path_escape_rejected', 'duplicate_rejected',
            'setuid_rejected', 'symlink_rejected', 'COPY_only_Dockerfile',
            'restrictive_umask_still_allows_nonroot_directory_traversal', 'owned_fixture_removed'],
        'downloads_builds_installs_containers_external_code_execution': 0}
    (Path(__file__).parent / 'component-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
