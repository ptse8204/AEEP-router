"""Maintain only installer-owned entry points; preserve runtime and audit data."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from .errors import ConfigurationError
from .onboarding import disconnect, list_connections


def maintain(operation: str) -> dict[str, Any]:
    root = Path(os.environ.get('AEEP_DATA_HOME', str(Path.home() / '.local/share/aeep'))).resolve()
    if operation == 'uninstall':
        results = [disconnect(c.connection_id) for c in list_connections() if c.enabled]
        marker = root / 'installation.json'
        if marker.exists():
            value = json.loads(marker.read_text())
            launcher = Path(value['launcher'])
            if launcher.exists():
                if hashlib.sha256(launcher.read_bytes()).hexdigest() != value['launcher_digest']:
                    raise ConfigurationError('connections revoked; edited launcher preserved')
                launcher.unlink()
        return {'status': 'disconnected', 'connections': results,
                'preserved': 'runtimes, selected third-party packages, receipts, grants and recovery records',
                'cleanup': 'Inspect AEEP-owned retained runtime directories before removing them.'}
    if operation != 'update':
        raise ConfigurationError('operation must be update or uninstall')
    def download(url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ConfigurationError('release metadata exceeds its size ceiling')
        return bytes(data)
    release = json.loads(download('https://api.github.com/repos/ptse8204/AEEP-router/releases/latest'))
    assets = {a['name']: a['browser_download_url'] for a in release.get('assets', [])}
    if not {'install.sh', 'SHA256SUMS'} <= assets.keys():
        raise ConfigurationError('latest published release has no verified installer assets; existing installation preserved')
    prefix = 'https://github.com/ptse8204/AEEP-router/releases/download/'
    if any(not assets[name].startswith(prefix) for name in ('install.sh', 'SHA256SUMS')):
        raise ConfigurationError('release artifact origin mismatch')
    hashes = download(assets['SHA256SUMS']).decode().splitlines()
    matching = [line.split()[0] for line in hashes if line.split()[1:] == ['install.sh']]
    if len(matching) != 1:
        raise ConfigurationError('release must identify exactly one installer checksum')
    with tempfile.TemporaryDirectory(prefix='aeep-update-') as directory:
        installer = Path(directory) / 'install.sh'
        installer.write_bytes(download(assets['install.sh']))
        install_release(installer, matching[0])
    return {'status': 'updated', 'tag': release['tag_name'], 'host_reload': 'required'}


def install_release(installer: Path, expected_sha256: str) -> None:
    if hashlib.sha256(installer.read_bytes()).hexdigest() != expected_sha256:
        raise ConfigurationError('installer digest does not match the reviewed release')
    subprocess.run(['sh', str(installer.resolve())], check=True)
