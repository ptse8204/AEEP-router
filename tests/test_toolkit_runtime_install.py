"""Private installer lifecycle; synthetic wheels are not evaluator conformance."""
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from test_toolkit_installation import manifest, policy

from aeep_toolkit import install_runtime as runtime
from aeep_toolkit.cli import main
from aeep_toolkit.installation import preview
from aeep_toolkit.models import ExtensionRegistry


def installation(tmp_path, *, extra=None, requires=''):
    wheelhouse = tmp_path / 'wheels'
    wheelhouse.mkdir()
    filename = 'aeep_installer_fixture-1.0-py3-none-any.whl'
    wheel = wheelhouse / filename
    entries = {
        'aeep_installer_fixture/__init__.py': 'VALUE = "synthetic"\n',
        'aeep_installer_fixture-1.0.dist-info/METADATA': 'Metadata-Version: 2.1\nName: aeep-installer-fixture\nVersion: 1.0\n' + requires,
        'aeep_installer_fixture-1.0.dist-info/WHEEL': 'Wheel-Version: 1.0\nGenerator: AEEP synthetic test\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
    } | (extra or {})
    record = 'aeep_installer_fixture-1.0.dist-info/RECORD'
    entries[record] = ''.join(f'{name},,\n' for name in [*entries, record])
    with zipfile.ZipFile(wheel, 'w') as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
    item = manifest(source=manifest().source.model_dump() | {'artifact_sha256': sha})
    rules = policy(item)
    selection = preview(ExtensionRegistry(extensions=(item,)), ('engine',), rules)
    wheels = (runtime.Wheel(extension_id='engine', filename=filename, name='aeep-installer-fixture', version='1.0', sha256=sha),)
    return runtime.prepare(selection, rules, tmp_path/'runtime', wheelhouse, wheels)


def fake_install(monkeypatch):
    def create(self, target):
        (target/'payload.txt').write_text('owned')
    monkeypatch.setattr(runtime.venv.EnvBuilder, 'create', create)
    monkeypatch.setattr(runtime, 'run', lambda *args: None)


def test_real_offline_install_replay_and_conflict_safe_remove(tmp_path):
    plan = installation(tmp_path)
    review = runtime.digest(plan)
    state = runtime.apply(plan, review)
    assert state['status'] == 'installed' and state['enabled'] is False
    assert runtime.apply(plan, review) == state
    root = Path(plan.destination)
    candidate = next(root.glob('lib/python*/site-packages/aeep_installer_fixture/__init__.py'))
    original = candidate.read_bytes()
    candidate.write_text('user edit')
    with pytest.raises(ValueError, match='preserved'):
        runtime.remove(plan, review)
    assert candidate.read_text() == 'user edit'
    candidate.write_bytes(original)
    removed = runtime.remove(plan, review)
    assert removed['status'] == 'removed' and not root.exists()
    assert runtime.remove(plan, review) == removed
    assert runtime.paths(plan)[1].exists()
    with pytest.raises(ValueError, match='no automatic retry'):
        runtime.apply(plan, review)


def test_preview_no_effects_and_review_before_effects(tmp_path, monkeypatch):
    plan = installation(tmp_path)
    before = runtime.snapshot(tmp_path)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **kw: pytest.fail('preview executed a process'))
    again = runtime.prepare(plan.preview, plan.policy, Path(plan.destination), Path(plan.wheelhouse), plan.wheels)
    assert again == plan and runtime.snapshot(tmp_path) == before
    with pytest.raises(ValueError, match='review'):
        runtime.apply(plan, '0' * 64)
    assert runtime.snapshot(tmp_path) == before


@pytest.mark.parametrize('extra', [
    {'../escape': 'x'}, {'evil.pth': 'import os'}, {'sitecustomize/__init__.py': 'x'},
    {'pip/__init__.py': 'x'}, {'fixture.data/scripts/python': 'x'}, {'/absolute': 'x'}, {'back\\slash': 'x'},
])
def test_unsafe_wheel_rejected_before_effects(tmp_path, extra):
    with pytest.raises(ValueError, match='unsupported'):
        installation(tmp_path, extra=extra)
    assert not (tmp_path/'runtime').exists()


def test_incomplete_dependency_lock_fails_offline_and_keeps_journal(tmp_path):
    plan = installation(tmp_path, requires='Requires-Dist: aeep-fixture-absent-dependency==7.0\n')
    with pytest.raises(subprocess.CalledProcessError):
        runtime.apply(plan, runtime.digest(plan))
    _, state = runtime.load_state(runtime.paths(plan)[1])
    assert state['status'] == 'failed'
    with pytest.raises(ValueError, match='no automatic retry'):
        runtime.apply(plan, runtime.digest(plan))
    assert Path(plan.destination).exists()


@pytest.mark.parametrize('change', ['wheel', 'interpreter', 'platform', 'space', 'existing', 'link'])
def test_drift_and_conflicts_prevent_installation(tmp_path, monkeypatch, change):
    from aeep import component_setup
    from aeep.errors import ConfigurationError
    plan = installation(tmp_path)
    if change == 'wheel':
        (Path(plan.wheelhouse)/plan.wheels[0].filename).write_bytes(b'changed')
    elif change == 'interpreter':
        plan.interpreter_sha256 = '0' * 64
    elif change == 'platform':
        plan.machine = 'unsupported'
    elif change == 'space':
        monkeypatch.setattr(component_setup, 'require_space', lambda *a: (_ for _ in ()).throw(ConfigurationError('reserve')))
    elif change == 'existing':
        Path(plan.destination).mkdir()
        (Path(plan.destination)/'user').write_text('keep')
    else:
        Path(plan.destination).symlink_to(Path(plan.wheelhouse), target_is_directory=True)
    fake_install(monkeypatch)
    with pytest.raises((ValueError, ConfigurationError)):
        runtime.apply(plan, runtime.digest(plan))
    if change == 'existing':
        assert (Path(plan.destination)/'user').read_text() == 'keep'
    assert not runtime.paths(plan)[1].exists() if change != 'link' else True


def test_failure_after_effects_retained_and_not_replayed(tmp_path, monkeypatch):
    plan = installation(tmp_path)
    fake_install(monkeypatch)
    monkeypatch.setattr(runtime, 'run', lambda *args: (_ for _ in ()).throw(TimeoutError('synthetic')))
    with pytest.raises(TimeoutError):
        runtime.apply(plan, runtime.digest(plan))
    assert runtime.load_state(runtime.paths(plan)[1])[1]['status'] == 'failed'
    with pytest.raises(ValueError, match='no automatic retry'):
        runtime.apply(plan, runtime.digest(plan))
    with pytest.raises(ValueError, match='preserved'):
        runtime.remove(plan, runtime.digest(plan))


@pytest.mark.parametrize('change', ['added', 'missing', 'mode', 'symlink', 'hardlink', 'fifo', 'credentials'])
def test_removal_preserves_changed_runtime(tmp_path, monkeypatch, change):
    plan = installation(tmp_path)
    fake_install(monkeypatch)
    runtime.apply(plan, runtime.digest(plan))
    root = Path(plan.destination)
    if change == 'added':
        (root/'user').write_text('keep')
    elif change == 'missing':
        (root/'payload.txt').unlink()
    elif change == 'mode':
        (root/'payload.txt').chmod(0o700)
    elif change == 'symlink':
        (root/'outside').symlink_to(tmp_path/'wheels', target_is_directory=True)
    elif change == 'hardlink':
        os.link(root/'payload.txt', root/'linked')
    elif change == 'credentials':
        (root/'auth.json').write_text('never-read')
    else:
        os.mkfifo(root/'pipe')
    with pytest.raises(ValueError):
        runtime.remove(plan, runtime.digest(plan))
    assert root.exists()


def test_tampered_preview_and_selection_rejected(tmp_path):
    plan = installation(tmp_path)
    data = plan.model_dump(mode='json')
    data['preview']['items'][0]['manifest']['source']['license_expression'] = 'unreviewed'
    with pytest.raises(ValueError):
        runtime.RuntimeInstallation.model_validate(data)
    data = plan.model_dump(mode='json')
    data['wheels'][0]['extension_id'] = 'unselected'
    with pytest.raises(ValueError):
        runtime.RuntimeInstallation.model_validate(data)


def test_cli_journey(tmp_path, capsys, monkeypatch):
    plan = installation(tmp_path)
    for name, value in [('preview', plan.preview.model_dump(mode='json')), ('policy', plan.policy.model_dump(mode='json')),
                        ('wheels', [w.model_dump(mode='json') for w in plan.wheels])]:
        (tmp_path/f'{name}.json').write_text(json.dumps(value))
    assert main(['install-plan', '--preview', str(tmp_path/'preview.json'), '--policy', str(tmp_path/'policy.json'),
                 '--wheels', str(tmp_path/'wheels.json'), '--wheelhouse', plan.wheelhouse, '--destination', plan.destination]) == 0
    output = json.loads(capsys.readouterr().out)
    document = tmp_path/'installation.json'
    document.write_text(json.dumps(output))
    fake_install(monkeypatch)
    for operation in ('install', 'remove'):
        assert main([operation, '--installation', str(document), '--reviewed-digest', output['review_sha256']]) == 0
        assert json.loads(capsys.readouterr().out)['status'] == ('installed' if operation == 'install' else 'removed')
