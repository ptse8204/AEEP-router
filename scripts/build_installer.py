"""Build, never publish, versioned installer assets with hashed dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--uv', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not args.tag.startswith('v') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in args.tag):
        parser.error('tag must be an explicit version tag')
    root = Path(__file__).resolve().parents[1]
    from aeep.component_setup import require_space
    require_space(args.output, 1024**3)
    bundle = args.output.resolve() / 'bundle'
    bundle.mkdir(parents=True, exist_ok=False)
    subprocess.run([sys.executable, '-m', 'build', '--wheel', '--outdir', str(bundle)], cwd=root, check=True)
    subprocess.run([str(args.uv.resolve()), 'pip', 'compile', 'pyproject.toml', '--universal', '--python-version', '3.12',
                    '--generate-hashes', '--output-file', str(bundle / 'requirements.txt')], cwd=root, check=True)
    shutil.copyfile(root / 'scripts/finish_install.py', bundle / 'finish_install.py')
    wheel = next(bundle.glob('*.whl'))
    metadata = {'tag': args.tag, 'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)),
                'wheel': wheel.name, 'python': '3.12.11', 'uv': '0.8.22',
                'uv_targets': {'darwin-arm64': 'aarch64-apple-darwin', 'darwin-x86_64': 'x86_64-apple-darwin',
                               'linux-aarch64': 'aarch64-unknown-linux-gnu', 'linux-x86_64': 'x86_64-unknown-linux-gnu'},
                'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()}}
    (bundle / 'release.json').write_text(json.dumps(metadata, indent=2) + '\n')
    archive = args.output / 'aeep-bundle.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        stream.add(bundle, arcname='bundle')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    script = (root / 'scripts/install.sh').read_text().replace('@RELEASE_BASE@', f'https://github.com/ptse8204/AEEP-router/releases/download/{args.tag}').replace('@BUNDLE_SHA256@', digest)
    # Keep the shell script byte-identical to its checksum on Windows too.
    (args.output / 'install.sh').write_bytes(script.encode('utf-8'))
    (args.output / 'SHA256SUMS').write_text(f'{digest}  aeep-bundle.tar.gz\n' + hashlib.sha256(script.encode()).hexdigest() + '  install.sh\n')
    print(f'Prepared {args.output}; publication and clean-source live platform checks remain separate.')


if __name__ == '__main__':
    main()
