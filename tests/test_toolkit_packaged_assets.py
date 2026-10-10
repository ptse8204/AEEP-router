"""Package layout and source identity without installing or executing a new wheel."""
import hashlib
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep.assessment import verification
from aeep.errors import ConfigurationError
from aeep_toolkit import cli


def test_installed_scripted_cli_uses_standard_data_location(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, '__file__', str(tmp_path/'site-packages/aeep_toolkit/cli.py'))
    monkeypatch.setattr(cli.sysconfig, 'get_path', lambda name: str(tmp_path/'prefix'))
    script = tmp_path/'prefix/share/aeep/integrations/toolkit/evaluate.py'
    script.parent.mkdir(parents=True)
    script.write_text('# synthetic layout only')
    calls = []
    def run(argv, *, check):
        calls.append(argv)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cli.subprocess, 'run', run)
    assert cli.main(['eval', 'scripted', 'plan']) == 0
    assert calls == [[sys.executable, '-B', str(script), 'plan']]


def test_installed_digest_tracks_both_namespaces_and_assets(tmp_path, monkeypatch):
    site = tmp_path/'lib/python3.13/site-packages'
    module = site/'aeep/assessment/verification.py'
    module.parent.mkdir(parents=True)
    module.write_text('owned implementation')
    toolkit = site/'aeep_toolkit/candidate.py'
    toolkit.parent.mkdir()
    toolkit.write_text('candidate')
    assets = tmp_path/'share/aeep/integrations/toolkit/evaluate.py'
    assets.parent.mkdir(parents=True)
    assets.write_text('bridge')
    monkeypatch.setattr(verification, '__file__', str(module))
    monkeypatch.setattr(verification.sysconfig, 'get_path', lambda name: str(tmp_path))
    root = module.parents[3]
    before = verification.verification_source_digest(root)
    assert before != hashlib.sha256().hexdigest()
    for file in (module, toolkit, assets):
        file.write_text(file.read_text()+' changed')
        after = verification.verification_source_digest(root)
        assert before != after
        before = after
    cache = toolkit.parent/'__pycache__'
    cache.mkdir()
    (cache/'candidate.cpython-313.pyc').write_bytes(b'cache')
    assert verification.verification_source_digest(root) == before
    assets.unlink()
    assets.symlink_to(module)
    with pytest.raises(ConfigurationError, match='links'):
        verification.verification_source_digest(root)
    assets.unlink()
    assets.parent.rmdir()
    assets.parent.parent.rmdir()
    with pytest.raises(ConfigurationError, match='unavailable'):
        verification.verification_source_digest(root)


def test_bridge_package_inventory_contains_runtime_sources_and_exact_fixture_tree():
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root/'pyproject.toml').read_text())
    files = config['tool']['setuptools']['data-files']
    bridge = set(files['share/aeep/integrations/toolkit'])
    required = {str(path.relative_to(root)) for path in (root/'integrations/toolkit').glob('*.py')
                if not path.name.startswith('test_')}
    assert required <= bridge
    fixtures = {file for target, names in files.items() if target.startswith('share/aeep/integrations/toolkit/fixtures') for file in names}
    stack = cli.read_json(root/'integrations/toolkit/stack.json')
    assert fixtures == {'integrations/toolkit/'+name for name in stack['fixtures']}
    for name in bridge | fixtures:
        assert (root/name).is_file()
