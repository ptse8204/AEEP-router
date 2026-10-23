"""Cache exact official portable wheel data; no installation/import of subjects."""
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
CACHE = ROOT / '.aeep/repository-corpus-expansion-20261022-wheels'
PINS = {'gast': '0.6.0', 'uritemplate': '4.2.0', 'pytest-asyncio': '1.2.0', 'pylatexenc': '3.0a33'}


def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 10 * 1024**2
    CACHE.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('aeep_read_only_wheel_metadata', HERE.parent / 'repository-replacement-runtime-20261022/prepare-runtime-wheels.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.HERE, helper.CACHE = HERE, CACHE
    def prepare(item):
        try:
            value = helper.prepare(item)
            assert value['filename'].endswith('-none-any.whl') and value['size_bytes'] <= 650_000
            return value
        except Exception as exc:
            return {'project': item[0], 'version': item[1], 'error_type': type(exc).__name__, 'error': str(exc)[:180]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(prepare, PINS.items()))
    existing = json.loads((HERE.parent / 'repository-replacement-runtime-20261022/runtime-wheel-review.json').read_text())['pins']
    available = {canonicalize_name(x['project']): x['version'] for x in [*existing, *values] if 'error_type' not in x}
    checks = []
    for value in values:
        if 'error_type' in value:
            continue
        for raw in value['requires_dist']:
            req = Requirement(raw)
            if req.marker and not req.marker.evaluate({**helper.ENV, 'extra': ''}):
                continue
            selected = available.get(canonicalize_name(req.name))
            checks.append({'project': value['project'], 'requires': raw, 'selected': selected, 'satisfied': selected is not None and Version(selected) in req.specifier})
    report = {'pins': values, 'active_requirement_checks': checks, 'closure_verified': all(x['satisfied'] for x in checks) and all('error_type' not in x for x in values),
              'downloaded_wheel_bytes': sum(x.get('size_bytes', 0) for x in values), 'external_code_executed': False,
              'installations': 0, 'policy': 'Official source hashes, portable tags, bounded wheel/metadata bytes and retained license texts. Cache is inert; execution requires exact review.'}
    (HERE / 'pure-wheel-review.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pins': [{k: x.get(k) for k in ('project', 'version', 'filename', 'error_type', 'error')} for x in values], 'closure_verified': report['closure_verified']}))


if __name__ == '__main__':
    main()
