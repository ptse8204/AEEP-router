"""Audit only the React dependency payload in two already built local images."""

import hashlib
import io
import json
import runpy
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
old = runpy.run_path(str(HERE / 'worker-runtime.py'))
read, image, save = (old[k] for k in ('read', 'image', 'save'))
PFX = 'opt/aeep-task-tools/react/'
maximum_blob = 2 * 1024**3


def inspect_blob(layer):
    files, directories = {}, {}
    with tarfile.open(fileobj=layer, mode='r|*') as tree:
        for entry in tree:
            name = entry.name.removeprefix('./').lstrip('/')
            if not name.startswith(PFX):
                continue
            name = name.removeprefix(PFX).rstrip('/')
            if not name:
                continue
            assert str(PurePosixPath(name)) == name and '..' not in PurePosixPath(name).parts
            assert name not in files and name not in directories
            mode = entry.mode & 0o7777
            if entry.isdir():
                directories[name] = [mode, entry.uid, entry.gid]
                continue
            assert entry.isfile()
            with tree.extractfile(entry) as content:
                digest = hashlib.file_digest(content, 'sha256').hexdigest()
            files[name] = {'sha256': digest, 'bytes': entry.size, 'executable': bool(mode & 0o111),
                           'permissions': [mode, entry.uid, entry.gid]}
    return files, directories


def verify():
    review = read(old['REVIEW'])
    assert shutil.disk_usage(old['ROOT']).free >= 52 * 1024**3
    images = {role: image(row['tag']) for role, row in review['roles'].items()}
    assert all(item and item['platform'] == 'linux/arm64' and item['user'] == '65534:65534'
               and not item['volumes'] and item['layers'][:-1] == review['roles'][role]['parent']['layers']
               for role, item in images.items())
    assert images['control']['layers'][-1] != images['candidate']['layers'][-1]
    manifests = {row['id'].split(':')[-1] for row in images.values()}
    layers, layer_files = {}, {}
    total = 0
    tags = [row['tag'] for row in review['roles'].values()]
    proc = subprocess.Popen([*old['DOCKER'], 'image', 'save', '--platform', 'linux/arm64', *tags],
                            env=old['ENV'], cwd=old['WORK'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with tarfile.open(fileobj=proc.stdout, mode='r|') as export:
            for blob in export:
                assert shutil.disk_usage(old['ROOT']).free >= 50 * 1024**3
                if not blob.isfile():
                    continue
                total += blob.size
                assert total <= 5 * 1024**3 and blob.size <= maximum_blob
                parts = PurePosixPath(blob.name).parts
                if len(parts) != 3 or parts[:2] != ('blobs', 'sha256'):
                    continue
                name = parts[-1]
                with io.BufferedReader(export.extractfile(blob)) as payload:
                    if name in manifests:
                        assert blob.size <= 65536
                        content = payload.read()
                        assert hashlib.sha256(content).hexdigest() == name
                        layers[name] = json.loads(content)['layers'][-1]['digest'].split(':')[-1]
                    elif payload.peek(512).startswith(b'\x1f\x8b'):
                        files, dirs = inspect_blob(payload)
                        if files:
                            layer_files[name] = (files, dirs)
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
    compare = {role: layer_files[layers[item['id'].split(':')[-1]]] for role, item in images.items()}
    assert compare['control'] == compare['candidate']
    expected = {name: facts for name, facts in old['inventory'](old['CONTEXT']).items() if name.startswith('node_modules/')}
    actual = {name: {k: v for k, v in facts.items() if k != 'permissions'}
              for name, facts in compare['control'][0].items()}
    assert actual == expected
    record = {
        'images': images, 'identical_dependency_bytes_modes_and_ownership': True,
        'matches_frozen_context': True, 'dependency_files': len(actual), 'export_payload_bytes': total,
        'filesystem_inventory_sha256': old['content_digest'](compare['control']),
        'builds': 0, 'containers': 0, 'models': 0, 'raw_export_retained': False,
    }
    save(HERE / 'worker-image-parity.json', record)
    print(json.dumps({k: v for k, v in record.items() if k != 'images'}))


if __name__ == '__main__':
    verify()
