"""Read only the owned grader image's Debian package data; start no container."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
IMAGE = 'sha256:9f473c493b7af1854922807d2acbdcbe3b955313dc57f203e6f73c9c50f9ea85'
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def main():
    info = json.loads(subprocess.check_output([*DOCKER, 'image', 'inspect', IMAGE], timeout=20))[0]
    assert info['Id'] == IMAGE and info['Architecture'] == 'arm64' and info['Os'] == 'linux'
    free = shutil.disk_usage(ROOT).free
    assert free > 50 * 1024**3 + info['Size'] * 3
    scratch = ROOT / '.aeep/repository-git-image-inventory-20261028'
    resume = sys.argv[1:] == ['--read-existing-export']
    assert not sys.argv[1:] or resume
    if not resume:
        scratch.mkdir(exist_ok=False)
    archive = scratch / 'owned-grader-image.tar'
    if not resume:
        with archive.open('xb') as stream:
            child = subprocess.run([*DOCKER, 'image', 'save', IMAGE], stdout=stream,
                stderr=subprocess.PIPE, timeout=120)
        assert child.returncode == 0, 'Preserve the owned partial export; no automatic retry'
    assert archive.is_file() and not archive.is_symlink()
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3
    with tarfile.open(archive) as outer:
        manifest = json.load(outer.extractfile('manifest.json'))
        assert len(manifest) == 1
        raw_config = outer.extractfile(manifest[0]['Config']).read()
        index = json.load(outer.extractfile('index.json'))
        assert len(index['manifests']) == 1 and index['manifests'][0]['digest'] == IMAGE
        raw_manifest = outer.extractfile('blobs/sha256/' + IMAGE.removeprefix('sha256:')).read()
        assert 'sha256:' + hashlib.sha256(raw_manifest).hexdigest() == IMAGE
        oci_manifest = json.loads(raw_manifest)
        assert oci_manifest['config']['digest'] == 'sha256:' + hashlib.sha256(raw_config).hexdigest()
        assert manifest[0]['Config'] == 'blobs/' + oci_manifest['config']['digest'].replace(':', '/')
        config = json.loads(raw_config)
        assert config['rootfs']['diff_ids'] == info['RootFS']['Layers']
        assert config['config'] == info['Config'] and config['architecture'] == info['Architecture']
        assert manifest[0]['Layers'] == ['blobs/' + item['digest'].replace(':', '/') for item in oci_manifest['layers']]
        status, origin = None, None
        for layer, descriptor in zip(manifest[0]['Layers'], oci_manifest['layers'], strict=True):
            assert 'sha256:' + hashlib.file_digest(outer.extractfile(layer), 'sha256').hexdigest() == descriptor['digest']
            with tarfile.open(fileobj=outer.extractfile(layer), mode='r|*') as inner:
                for member in inner:
                    if member.name.removeprefix('./') == 'var/lib/dpkg/status':
                        assert member.isfile() and member.size < 5_000_000
                        status = inner.extractfile(member).read().decode()
                        origin = layer
    assert status is not None
    packages = {}
    for paragraph in status.strip().split('\n\n'):
        fields = {}
        for line in paragraph.splitlines():
            if line and not line[0].isspace() and ': ' in line:
                key, value = line.split(': ', 1)
                fields[key] = value
        if fields.get('Status') == 'install ok installed':
            packages[fields['Package']] = {k: fields[k] for k in
                ('Version', 'Architecture', 'Depends', 'Pre-Depends') if k in fields}
    assert packages and 'git' not in packages
    assert hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() == digest
    size = archive.stat().st_size
    archive.unlink()
    scratch.rmdir()
    result = {'read_only_inventory': True, 'image_id': IMAGE, 'architecture': 'arm64',
        'image_size': info['Size'], 'layers': info['RootFS']['Layers'],
        'dpkg_status_last_layer': origin,
        'dpkg_status_sha256': hashlib.sha256(status.encode()).hexdigest(),
        'packages': packages, 'package_count': len(packages), 'git_absent': True,
        'owned_export_bytes': size, 'owned_export_sha256': digest,
        'read_existing_owned_export_without_second_export': resume,
        'oci_manifest_config_and_all_layer_digests_verified': True,
        'unchanged_owned_export_removed': not scratch.exists(),
        'containers_started_builds_installs_downloads_models': 0,
        'all_images_and_existing_containers_untouched': True,
        'free_before_bytes': free, 'free_after_bytes': shutil.disk_usage(ROOT).free}
    with (HERE / 'image-package-inventory.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('packages', 'layers')}))


if __name__ == '__main__':
    main()
