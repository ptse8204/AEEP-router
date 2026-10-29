"""Inspect existing image ELF data without starting a container or executing it."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'repository-review-bindings-20261029'
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']
IMAGE = 'sha256:9f473c493b7af1854922807d2acbdcbe3b955313dc57f203e6f73c9c50f9ea85'
NAMES = ('ld-linux-aarch64.so', 'libc.so.', 'libpcre2-8.so.', 'libz.so.')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    review = json.loads((OLD / 'runtime-review.json').read_text())
    objdump = Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/llvm-objdump')
    assert sha(objdump) == review['upstream_metadata']['objdump_sha256']
    image = json.loads(subprocess.check_output([*DOCKER, 'image', 'inspect', IMAGE], timeout=20))[0]
    assert image['Id'] == IMAGE and image['Architecture'] == 'arm64'
    free = shutil.disk_usage(ROOT).free
    assert free > 50 * 1024**3 + 3 * image['Size']
    scratch = ROOT / '.aeep/repository-cached-git-image-audit-20261029'
    scratch.mkdir(mode=0o700, exist_ok=False)
    archive = scratch / 'owned-image-data.tar'
    with archive.open('xb') as output:
        result = subprocess.run([*DOCKER, 'image', 'save', IMAGE], stdout=output,
            stderr=subprocess.PIPE, timeout=120)
    assert result.returncode == 0, 'Preserve owned partial export; no retry'
    archive_sha = sha(archive)
    nodes = {}
    with tarfile.open(archive) as outer:
        manifest = json.load(outer.extractfile('manifest.json'))
        index = json.load(outer.extractfile('index.json'))
        assert len(manifest) == len(index['manifests']) == 1
        assert index['manifests'][0]['digest'] == IMAGE
        raw_manifest = outer.extractfile('blobs/sha256/' + IMAGE.removeprefix('sha256:')).read()
        assert 'sha256:' + hashlib.sha256(raw_manifest).hexdigest() == IMAGE
        oci = json.loads(raw_manifest)
        raw_config = outer.extractfile(manifest[0]['Config']).read()
        assert 'sha256:' + hashlib.sha256(raw_config).hexdigest() == oci['config']['digest']
        config = json.loads(raw_config)
        assert config['rootfs']['diff_ids'] == image['RootFS']['Layers']
        assert config['config'] == image['Config']
        assert manifest[0]['Layers'] == ['blobs/' + x['digest'].replace(':', '/') for x in oci['layers']]
        for layer, descriptor in zip(manifest[0]['Layers'], oci['layers'], strict=True):
            assert 'sha256:' + hashlib.file_digest(outer.extractfile(layer), 'sha256').hexdigest() == descriptor['digest']
            with tarfile.open(fileobj=outer.extractfile(layer), mode='r|*') as inner:
                for member in inner:
                    name = member.name.removeprefix('./')
                    path = PurePosixPath(name)
                    assert not path.is_absolute() and '..' not in path.parts
                    if path.name == '.wh..wh..opq':
                        nodes = {n: v for n, v in nodes.items() if not n.startswith(str(path.parent) + '/')}
                    elif path.name.startswith('.wh.'):
                        target = str(path.parent / path.name.removeprefix('.wh.'))
                        nodes = {n: v for n, v in nodes.items() if n != target and not n.startswith(target + '/')}
                    elif name in ('lib', 'lib64', 'usr/lib') or (
                        name.startswith(('lib/', 'usr/lib/')) and path.name.startswith(NAMES)):
                        data = None
                        if member.isfile():
                            assert member.size <= 8 * 1024**2
                            data = inner.extractfile(member).read()
                        nodes[name] = {'kind': 'file' if member.isfile() else 'symlink' if member.issym()
                            else 'hardlink' if member.islnk() else 'directory',
                            'link': member.linkname, 'data': data, 'layer': descriptor['digest']}
    loader = nodes['usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1']
    assert loader['kind'] == 'file' and loader['data'].startswith(b'\x7fELF')
    assert nodes['lib']['kind'] == 'symlink' and nodes['lib']['link'] == 'usr/lib'
    assert nodes['usr/lib/ld-linux-aarch64.so.1']['kind'] == 'symlink'
    assert nodes['usr/lib/ld-linux-aarch64.so.1']['link'] == 'aarch64-linux-gnu/ld-linux-aarch64.so.1'
    outputs, temporary_files = {}, {}
    for index, (name, item) in enumerate(sorted(nodes.items())):
        if item['data'] is None:
            continue
        target = scratch / f'owned-ELF-data-{index}'
        target.write_bytes(item['data'])
        target.chmod(0o400)
        temporary_files[str(target)] = sha(target)
        value = subprocess.check_output([str(objdump), '-f', '-p', str(target)], text=True, timeout=20)
        assert 'elf64-littleaarch64' in value
        outputs[name] = {'sha256': sha(target), 'bytes': target.stat().st_size,
            'origin_layer': item['layer'], 'static_objdump': value}
    git = ROOT / review['build_context'] / 'git'
    git_inspection = subprocess.check_output([str(objdump), '-f', '-p', str(git)], text=True, timeout=20)
    git_interp = subprocess.check_output([str(objdump), '-s', '-j', '.interp', str(git)], text=True, timeout=20)
    assert sha(archive) == archive_sha
    size = archive.stat().st_size
    for name, expected in temporary_files.items():
        target = Path(name)
        assert target.is_file() and not target.is_symlink() and sha(target) == expected
        target.unlink()
    archive.unlink()
    scratch.rmdir()
    result = {'passed': True, 'image_id': IMAGE, 'inherited_config_and_all_layers_verified': True,
        'loader_present_in_parent': True, 'loader_canonical_path': 'usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1',
        'interpreter_aliases': {n: {k: v for k, v in item.items() if k != 'data'}
            for n, item in nodes.items() if item['kind'] != 'file'},
        'ELF_files': outputs, 'git_binary_sha256': sha(git),
        'git_static_objdump': git_inspection, 'git_interp_section': git_interp,
        'owned_export_bytes': size, 'owned_export_sha256': archive_sha,
        'owned_export_and_ELF_scratch_removed_unchanged': not scratch.exists(),
        'free_before_bytes': free, 'free_after_bytes': shutil.disk_usage(ROOT).free,
        'containers_builds_installs_downloads_models_or_linux_execution': 0,
        'all_images_and_existing_containers_untouched': True}
    with (HERE / 'parent-ELF-audit.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({k: result[k] for k in ('passed', 'loader_present_in_parent',
        'git_binary_sha256', 'owned_export_bytes', 'owned_export_and_ELF_scratch_removed_unchanged')}))


if __name__ == '__main__':
    main()
