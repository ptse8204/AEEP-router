"""Cache exact optional grader supports as inert data, without installation."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import shutil
import hashlib
import zipfile
from email.parser import BytesParser

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CACHE = ROOT / '.aeep/repository-test-root-wheels-20261027'
PINS = {'pbr': '7.0.1', 'jsonpath-rw-ext': '1.2.2', 'ply': '3.11', 'colorama': '0.4.6', 'arcp': '0.2.1', 'Jinja2': '3.1.6', 'MarkupSafe': '3.0.3', 'h2': '4.3.0', 'hpack': '4.1.0', 'hyperframe': '6.1.0', 'decorator': '5.2.1', 'setuptools': '75.8.2'}


def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 512 * 1024**2
    CACHE.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location('official_wheel_data_reader', HERE.parent / 'repository-replacement-runtime-20261022/prepare-runtime-wheels.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE, module.CACHE = HERE, CACHE
    def prepare(item):
        try:
            return module.prepare(item)
        except AssertionError:
            if item != ('ply', '3.11'):
                raise
            # The publisher wheel embeds its complete license in source headers.
            # Retain those bytes rather than infer a license from its filename.
            metadata_path = CACHE / 'ply.pypi.json'
            raw = metadata_path.read_bytes(); metadata = json.loads(raw)
            entry = next(e for e in metadata['urls'] if e['filename'] == 'ply-3.11-py2.py3-none-any.whl')
            path = CACHE / entry['filename']; data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry['digests']['sha256']
            with zipfile.ZipFile(path) as archive:
                message = BytesParser().parsebytes(archive.read('ply-3.11.dist-info/METADATA'))
                text = archive.read('ply/lex.py').decode()
            header = []
            for line in text.splitlines(keepends=True):
                if line.strip() and not line.startswith('#'):
                    break
                header.append(line)
            license = ''.join(header).encode()
            assert b'Redistribution and use in source and binary forms' in license
            assert b'THIS SOFTWARE IS PROVIDED' in license and b'All rights reserved.' in license
            destination = HERE / 'licenses/ply/LICENSE.embedded-source-header.txt'
            destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(license)
            return {'project': 'ply', 'version': '3.11', 'filename': entry['filename'],
                'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data), 'private_cache': str(path.relative_to(ROOT)),
                'source_url': entry['url'], 'metadata_url': 'https://pypi.org/pypi/ply/3.11/json',
                'metadata_sha256': hashlib.sha256(raw).hexdigest(), 'wheel_tags': ['py2-none-any', 'py3-none-any'],
                'requires_python': message.get('Requires-Python'), 'requires_dist': message.get_all('Requires-Dist', []),
                'license_metadata': message.get('License'), 'licenses': [{'wheel_path': 'ply/lex.py leading comments',
                    'retained': str(destination.relative_to(ROOT)), 'sha256': hashlib.sha256(license).hexdigest()}],
                'target': 'CPython3.13.15 Linux aarch64; static metadata only, not execution evidence'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pins = list(pool.map(prepare, PINS.items()))
    inherited = []
    manifests = [HERE.parent / 'repository-replacement-runtime-20261022/runtime-wheel-review.json', HERE.parent / 'repository-workload-batch-20261022/runtime-support-review.json', HERE.parent / 'repository-independent-sources-20261024/runtime-support-review.json', HERE.parent / 'repository-supported-suites-20261027/runtime-support-review.json']
    for path in manifests:
        inherited.extend(json.loads(path.read_text())['pins'])
    source = json.loads((HERE / 'jsonpath-source-review.json').read_text())
    inherited.append({'project': 'jsonpath-rw', 'version': source['distribution_version'], 'requires_python': None, 'requires_dist': source['install_requires_from_setup_ast'], 'source_only': True})
    values = {canonicalize_name(row['project']): row for row in [*inherited, *pins] if 'error_type' not in row}
    extras = {name: set() for name in values}
    extras['pydantic'].add('email')
    extras['httpx'].add('http2')
    checks, changed = {}, True
    while changed:
        changed = False
        for name, row in values.items():
            if row['requires_python']:
                assert Version(module.ENV['python_full_version']) in Requirement('python' + row['requires_python']).specifier
            for text in row['requires_dist']:
                requirement = Requirement(text)
                if requirement.marker and not any(requirement.marker.evaluate({**module.ENV, 'extra': extra}) for extra in {'', *extras[name]}):
                    continue
                target = canonicalize_name(requirement.name)
                checks[(name, text)] = {'project': name, 'requires': text, 'selected': values.get(target, {}).get('version'), 'satisfied': target in values and Version(values[target]['version']) in requirement.specifier}
                if target in values:
                    before = len(extras[target]); extras[target].update(requirement.extras)
                    changed |= before != len(extras[target])
    output = {'pins': pins, 'inherited_manifests': [str(path.relative_to(ROOT)) for path in manifests], 'active_requirement_checks': list(checks.values()), 'target_marker_environment': module.ENV, 'extras': {k: sorted(v) for k, v in extras.items() if v}, 'complete_static_dependency_closure': all('error_type' not in p for p in pins) and all(c['satisfied'] for c in checks.values()), 'downloaded_wheel_bytes': sum(p.get('size_bytes', 0) for p in pins), 'installations': 0, 'downloaded_code_imported': False, 'runtime_compatibility': 'UNVERIFIED; private optional grader supports only, not toolkit core. Exact build/execution review is still required.'}
    (HERE / 'runtime-support-review.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'pins': len(pins), 'bytes': output['downloaded_wheel_bytes'], 'closure': output['complete_static_dependency_closure'], 'errors': [p for p in pins if 'error_type' in p], 'unsatisfied': [c for c in checks.values() if not c['satisfied']]}))


if __name__ == '__main__':
    main()
