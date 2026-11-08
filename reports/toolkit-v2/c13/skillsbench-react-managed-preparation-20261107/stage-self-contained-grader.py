"""Assemble a private grader rootfs from the verified, never-started source container."""

import gzip
import hashlib
import json
import runpy
import shutil
import subprocess
import tarfile
import time
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
helper = runpy.run_path(str(HERE / 'worker-runtime.py'))
ROOT, WORK, read, sha, save = (helper[key] for key in ('ROOT', 'WORK', 'read', 'sha', 'save'))
CARRIER = helper['CARRIER']
ORIGINAL = ROOT / '.aeep' / CARRIER.name / 'context'
CALIBRATION = HERE.parent / 'skillsbench-react-nonroot-calibration-20261108'
TARGET = WORK / 'react-self-contained-amd64.rootfs.tar.gz'
MAX_BYTES = 7 * 1024**3
MIN_FREE = 50 * 1024**3
ADDITIONS = {
    'browser': 'opt/aeep-react-browser', 'python': 'opt/aeep-assessment-python',
    'protected': 'opt/aeep-react-reference',
    'aeep-assessment.pth': 'usr/local/lib/python3.12/dist-packages/aeep-assessment.pth',
}


class SourceStream:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.size = 0
        self.checked_at = 0
        self.started = time.monotonic()

    def read(self, length):
        chunk = self.stream.read(length)
        self.digest.update(chunk)
        self.size += len(chunk)
        assert self.size <= MAX_BYTES
        if self.size - self.checked_at >= 64 * 1024**2:
            assert shutil.disk_usage(ROOT).free >= MIN_FREE
            assert time.monotonic() - self.started < 600
            self.checked_at = self.size
        return chunk


def normalized_context_entry(entry):
    assert entry.isfile() or entry.isdir()
    entry.uid = entry.gid = 0
    entry.uname = entry.gname = 'root'
    entry.mtime = 0
    entry.mode = 0o555 if entry.isdir() or entry.mode & 0o111 else 0o444
    return entry


def inspect_source(cid):
    result = helper['docker']('container', 'inspect', '--format',
        '{{.Id}} {{.Image}} {{.State.Status}} {{.HostConfig.NetworkMode}} {{json .Mounts}} {{.State.StartedAt}}', cid)
    assert result.returncode == 0
    expected = [cid, helper['OLD']['parent_id'], 'created', 'none', '[]', '0001-01-01T00:00:00Z']
    assert result.stdout.strip().split() == expected
    return expected


def stage():
    assert shutil.disk_usage(ROOT).free >= 57 * 1024**3
    assert helper['docker']('system', 'df', '--format', '{{.Type}} {{.Size}}').returncode == 0
    context = runpy.run_path(str(CARRIER / 'stage-carrier.py'))
    assert helper['content_digest'](context['inventory']()) == helper['OLD']['context_sha256']
    assert not TARGET.exists()
    prior = read(CALIBRATION / 'browser-extraction.json')
    cid = prior['source_container_id']
    source = inspect_source(cid)
    proc = subprocess.Popen([*helper['DOCKER'], 'container', 'export', cid], env=helper['ENV'], cwd=WORK,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    incoming = SourceStream(proc.stdout)
    source_paths = set()
    digest = None
    try:
        with TARGET.open('xb') as compressed:
            with gzip.GzipFile(filename='', mode='wb', fileobj=compressed, compresslevel=1, mtime=0) as gzip_stream:
                with tarfile.open(fileobj=gzip_stream, mode='w|', format=tarfile.PAX_FORMAT) as output:
                    with tarfile.open(fileobj=incoming, mode='r|') as archive:
                        for entry in archive:
                            path = PurePosixPath(entry.name)
                            assert not path.is_absolute() and '..' not in path.parts
                            name = str(path)
                            assert name not in source_paths and len(source_paths) < 1_000_000
                            source_paths.add(name)
                            assert not any(name == dst or name.startswith(dst + '/') for dst in ADDITIONS.values())
                            output.addfile(entry, archive.extractfile(entry) if entry.isfile() else None)
                    for local, guest in ADDITIONS.items():
                        output.add(ORIGINAL / local, arcname=guest, filter=normalized_context_entry)
            while incoming.read(1024**2):
                pass
        assert proc.wait(timeout=20) == 0
        assert {'app', 'services/api-simulator', 'usr/local/lib/python3.12/dist-packages'} <= source_paths
        assert inspect_source(cid) == source
        assert shutil.disk_usage(ROOT).free >= MIN_FREE
        digest = sha(TARGET)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=20)
        if TARGET.exists():
            TARGET.chmod(0o400)
        save(HERE / 'self-contained-staging.json', {
            'source_container': cid, 'source_image': helper['OLD']['parent_id'],
            'source_export_bytes': incoming.size, 'source_export_sha256': incoming.digest.hexdigest(),
            'base_entries': len(source_paths), 'context_sha256': helper['OLD']['context_sha256'],
            'archive': str(TARGET), 'archive_bytes': TARGET.stat().st_size if TARGET.exists() else 0,
            'archive_sha256': digest, 'overlay_locations': ADDITIONS, 'passed': digest is not None,
            'source_container_started': False, 'imports': 0, 'builds': 0, 'models': 0,
        })
    print(json.dumps({'staged': True, 'sha256': digest, 'archive_bytes': TARGET.stat().st_size}))


if __name__ == '__main__':
    stage()
