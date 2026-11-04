"""Read only the new image-layer headers and the two reviewed public files."""
import hashlib
import io
import json
import subprocess
import tarfile


def stream(docker, image, consume):
    child = subprocess.Popen([*docker, 'image', 'save', image], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=child.stdout, mode='r|*') as archive:
            value = consume(archive)
        child.stdout.close()
        error = child.stderr.read()
        if child.wait(timeout=30):
            raise RuntimeError('Read-only image export failed: ' + hashlib.sha256(error).hexdigest())
        return value
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)


def audit(docker, image, files):
    def manifest(archive):
        result = None
        for member in archive:
            if member.name == 'manifest.json':
                result = json.load(archive.extractfile(member))
        assert result and len(result) == 1
        return result[0]
    record = stream(docker, image, manifest)
    selected = set(record['Layers'][-5:])
    expected = {
        'opt/dependencies/stack-check': ('directory', 0o555),
        'etc/codex/skills': ('directory', 0o555),
        'etc/codex/skills/stack-check': ('symlink', 0o777),
        **{name.lstrip('/'): ('file', 0o444) for name in files},
    }
    def layers(archive):
        seen = {}
        count = 0
        for member in archive:
            if member.name not in selected:
                continue
            count += 1
            with tarfile.open(fileobj=archive.extractfile(member), mode='r|*') as layer:
                for item in layer:
                    name = item.name.removeprefix('./').rstrip('/')
                    if name not in expected:
                        # New layers may contain ancestor-directory headers only.
                        assert item.isdir() and name in {'opt', 'opt/dependencies', 'etc', 'etc/codex'}, name
                        continue
                    kind = 'directory' if item.isdir() else 'symlink' if item.issym() else 'file' if item.isfile() else 'other'
                    value = {'kind': kind, 'mode': item.mode & 0o7777}
                    if item.issym():
                        assert item.linkname == '/opt/dependencies/stack-check'
                        value['target'] = item.linkname
                    if item.isfile():
                        value['sha256'] = hashlib.sha256(layer.extractfile(item).read()).hexdigest()
                        assert value['sha256'] == files['/' + name]
                    seen[name] = value
        assert count == 5 and set(seen) == set(expected)
        for name, (kind, mode) in expected.items():
            assert (seen[name]['kind'], seen[name]['mode']) == (kind, mode), name
        return {'passed': True, 'image': image, 'new_layer_count': count, 'final_entries': seen,
                'base_layer_contents_read': False, 'linux_code_executed': False,
                'credential_or_volume_contents_read': False, 'archive_retained': False}
    return stream(docker, image, layers)
