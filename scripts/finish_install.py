"""Finish a checksum-verified installation; no third-party host authentication."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    bundle, staging, root = (Path(p).resolve() for p in sys.argv[1:4])
    metadata = json.loads((bundle / 'release.json').read_text())
    for name, digest in metadata['files'].items():
        path = bundle / name
        if path.resolve().parent != bundle or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SystemExit('Release file checksum mismatch')
    wheel = bundle / metadata['wheel']
    uv = staging.parent / ('uv-' + metadata['uv_targets'][sys.platform + '-' + os.uname().machine]) / 'uv'
    subprocess.run([str(uv), 'pip', 'install', '--python', str(staging / 'bin/python'), '--no-deps', str(wheel)], check=True)
    subprocess.run([str(staging / 'bin/python'), '-I', '-m', 'aeep', 'version'], check=True)
    active = root / 'venv'
    existing_marker = root / 'installation.json'
    if existing_marker.exists():
        existing = json.loads(existing_marker.read_text())
        if existing.get('files') == metadata['files'] and active.exists():
            run_setup(active / 'bin/python')
            return
    rollback = root / ('rollback-' + hashlib.sha256(json.dumps(metadata['files'], sort_keys=True).encode()).hexdigest()[:12])
    if rollback.exists():
        raise SystemExit('Rollback path already exists; preserved. Inspect it before updating again.')
    if active.exists() or active.is_symlink():
        active.rename(rollback)
    # Keep the environment at its creation path: venv scripts contain absolute shebangs.
    temporary = root / ('venv.next-' + staging.parent.name)
    try:
        temporary.symlink_to(staging)
        temporary.replace(active)
        binary = Path.home().resolve() / '.local/bin/aeep'
        if binary.is_symlink() or (binary.exists() and binary.stat().st_nlink != 1):
            raise SystemExit('Existing launcher is a symlink or hard link; preserved.')
        binary.parent.mkdir(parents=True, exist_ok=True)
        wrapper = f'#!/bin/sh\nexec {shlex.quote(str(active / "bin/python"))} -I -m aeep "$@"\n'
        if binary.exists() and not binary.read_text().startswith('#!/bin/sh\n# AEEP launcher\n'):
            raise SystemExit('Existing ~/.local/bin/aeep is not owned by this installer; preserved.')
        binary.write_text(wrapper.replace('#!/bin/sh\n', '#!/bin/sh\n# AEEP launcher\n', 1))
        binary.chmod(0o755)
        installed = {**metadata, 'runtime': str(staging), 'previous_runtime': str(rollback) if rollback.exists() else None,
                     'launcher': str(binary), 'launcher_digest': hashlib.sha256(binary.read_bytes()).hexdigest()}
        (root / 'installation.json').write_text(json.dumps(installed, indent=2) + '\n')
    except BaseException:
        if active.is_symlink():
            active.unlink()
        if rollback.exists():
            rollback.rename(active)
        raise
    run_setup(active / 'bin/python')
    print(f'Installed AEEP. Run {binary} to open the menu. Restart connected agents.')
    if shutil.which('aeep') != str(binary):
        print('Add ~/.local/bin to PATH to use the short aeep command; the full path works now.')


def run_setup(python: Path) -> None:
    command = [str(python), '-I', '-m', 'aeep', 'setup', *sys.argv[4:]]
    if not sys.stdin.isatty() and '--yes' not in command:
        with open('/dev/tty') as terminal:
            subprocess.run(command, stdin=terminal, check=True)
    else:
        subprocess.run(command, check=True)



if __name__ == '__main__':
    main()
