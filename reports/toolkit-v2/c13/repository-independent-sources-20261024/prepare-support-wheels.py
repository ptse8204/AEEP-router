"""Cache exact optional grader supports as inert data, without installation."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import shutil

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CACHE = ROOT / '.aeep/repository-independent-supports-20261024'
PINS = {
    'SQLAlchemy': '2.0.44', 'greenlet': '3.2.4', 'inflect': '7.5.0',
    'more-itertools': '10.8.0', 'typeguard': '4.4.4',
    'msgspec': '0.19.0', 'httpx': '0.28.1', 'httpx-ws': '0.7.2',
    'httpcore': '1.0.9', 'anyio': '4.11.0', 'sniffio': '1.3.1',
    'wsproto': '1.2.0', 'h11': '0.16.0', 'pytest-subtests': '0.14.2',
    'arrow': '1.4.0', 'requests-mock': '1.12.1',
}


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
        except Exception as exc:
            return {'project': item[0], 'version': item[1], 'error_type': type(exc).__name__, 'error': str(exc)[:200]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pins = list(pool.map(prepare, PINS.items()))
    inherited = []
    manifests = [HERE.parent / 'repository-replacement-runtime-20261022/runtime-wheel-review.json', HERE.parent / 'repository-workload-batch-20261022/runtime-support-review.json']
    for path in manifests:
        inherited.extend(json.loads(path.read_text())['pins'])
    values = {canonicalize_name(row['project']): row for row in [*inherited, *pins] if 'error_type' not in row}
    extras = {name: set() for name in values}
    extras['pydantic'].add('email')
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
