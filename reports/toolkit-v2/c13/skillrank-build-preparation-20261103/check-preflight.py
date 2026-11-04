"""First-party authority/drift controls on temporary metadata; no Docker/network."""
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prepared_runtime', HERE / 'run-runtime.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_disk = shutil.disk_usage
rows = []
with tempfile.TemporaryDirectory(prefix='aeep-skillrank-preflight-') as work:
    root = Path(work).resolve()
    module.HERE = root
    module.ROOT = root
    module.verification_source_digest = lambda path: 'a' * 64
    module.shutil.disk_usage = lambda path: type(original_disk(path))(100 * 1024**3, 30 * 1024**3, 70 * 1024**3)
    asset = root / 'input'
    asset.write_text('first-party fixture')
    context = root / 'context'
    context.mkdir()
    alias = root / 'executable-alias'
    alias.symlink_to(asset)
    checks = root / 'checks.json'
    gate = {'source_before': 'a' * 64, 'source_after': 'a' * 64,
            'checks': [{'exit_code': 0} for _ in range(13)]}
    checks.write_text(json.dumps(gate))
    review = {'assets': {str(asset): hashlib.sha256(asset.read_bytes()).hexdigest()},
        'executable_links': {str(alias): str(asset)},
        'source': 'a' * 64, 'build_context': str(context),
        'build_context_sha256': module.tree_hash(context), 'source_checks': str(checks),
        'expires_at': '2026-11-06T12:00:00Z'}
    review_file = root / 'operation-review.json'
    review_file.write_text(json.dumps(review))
    assert module.validate() == review
    rows.append('valid metadata preflight consumes no execution attempt')

    def rejected(label, mutate, restore):
        mutate()
        try:
            module.validate()
        except ValueError:
            assert not (root / 'runtime-started.json').exists()
            rows.append(label)
        else:
            raise AssertionError('Invalid preflight accepted: ' + label)
        finally:
            restore()

    rejected('asset drift', lambda: asset.write_text('changed'), lambda: asset.write_text('first-party fixture'))
    rejected('coordinator drift', lambda: setattr(module, 'verification_source_digest', lambda p: 'b' * 64),
             lambda: setattr(module, 'verification_source_digest', lambda p: 'a' * 64))
    rejected('failed source gate', lambda: checks.write_text(json.dumps(gate | {'checks': [{'exit_code': 1}]*13})),
             lambda: checks.write_text(json.dumps(gate)))
    rejected('storage shortage', lambda: setattr(module.shutil, 'disk_usage', lambda p: type(original_disk(p))(100*1024**3,51*1024**3,49*1024**3)),
             lambda: setattr(module.shutil, 'disk_usage', lambda p: type(original_disk(p))(100*1024**3,30*1024**3,70*1024**3)))
    rejected('expired authority', lambda: review_file.write_text(json.dumps(review | {'expires_at': '2020-01-01T00:00:00Z'})),
             lambda: review_file.write_text(json.dumps(review)))
    link = context / 'link'
    rejected('source symlink', lambda: link.symlink_to(asset), lambda: link.unlink())
    other = root / 'different-executable'
    other.write_text('different first-party fixture')
    def point_alias(target):
        alias.unlink()
        alias.symlink_to(target)
    rejected('changed executable target', lambda: point_alias(other), lambda: point_alias(asset))
module.shutil.disk_usage = original_disk
payload = {'passed': True, 'controls': rows, 'count': len(rows), 'models': 0,
           'Docker_calls': 0, 'grant_or_attempt_created': False,
           'upstream_execution_proven': False}
(HERE / 'preflight-controls.json').write_text(json.dumps(payload, indent=2) + '\n')
print(json.dumps(payload))
