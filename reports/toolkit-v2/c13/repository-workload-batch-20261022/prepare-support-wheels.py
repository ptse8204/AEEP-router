"""Cache official exact runtime artifacts as inert bytes, without installation."""
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
CACHE = ROOT / '.aeep/repository-workload-batch-20261022-wheels'
PINS = {'pydantic':'2.12.3', 'pydantic-core':'2.41.4', 'annotated-types':'0.7.0',
        'typing-inspection':'0.4.2', 'email-validator':'2.3.0', 'dnspython':'2.8.0',
        'Django':'5.2.7', 'asgiref':'3.10.0', 'sqlparse':'0.5.3', 'pytest-django':'4.11.1',
        'attrs':'25.4.0', 'identify':'2.6.15', 'sybil':'9.2.0', 'pytest-asyncio':'1.2.0',
        'Markdown':'3.9', 'Faker':'37.11.0', 'model-bakery':'1.20.5',
        'python-dateutil':'2.9.0.post0', 'six':'1.17.0', 'django-debug-toolbar':'6.0.0', 'tzdata':'2025.2', 'pytz':'2025.2'}


def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 256 * 1024**2
    CACHE.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location('reviewed_wheel_data_reader', HERE.parent / 'repository-replacement-runtime-20261022/prepare-runtime-wheels.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE, module.CACHE = HERE, CACHE
    def prepare(item):
        try:
            return module.prepare(item)
        except Exception as exc:
            return {'project': item[0], 'version': item[1], 'error_type': type(exc).__name__, 'error': str(exc)[:200]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(prepare, PINS.items()))
    old = json.loads((HERE.parent / 'repository-replacement-runtime-20261022/runtime-wheel-review.json').read_text())['pins']
    values = {canonicalize_name(x['project']): x for x in [*old, *records] if 'error_type' not in x}
    extras = {name: set() for name in values}
    # Pydantic's email extra is explicitly required by the reviewed SCIM source.
    extras['pydantic'].add('email')
    checks, changed = {}, True
    while changed:
        changed = False
        for name, row in values.items():
            if row['requires_python']:
                assert Version(module.ENV['python_full_version']) in Requirement('python'+row['requires_python']).specifier
            for raw in row['requires_dist']:
                req = Requirement(raw)
                if req.marker and not any(req.marker.evaluate({**module.ENV, 'extra':extra}) for extra in {'', *extras[name]}):
                    continue
                target = canonicalize_name(req.name)
                checks[(name, raw)] = {'project':name, 'requires':raw, 'selected':values.get(target, {}).get('version'),
                    'satisfied': target in values and Version(values[target]['version']) in req.specifier}
                if target in values:
                    before=len(extras[target]); extras[target].update(req.extras); changed |= before != len(extras[target])
    report = {'pins':records, 'inherited_runtime_manifest':'reports/toolkit-v2/c13/repository-replacement-runtime-20261022/runtime-wheel-review.json',
        'active_requirement_checks':list(checks.values()), 'extras':{k:sorted(v) for k,v in extras.items() if v},
        'complete_static_dependency_closure': all('error_type' not in x for x in records) and all(x['satisfied'] for x in checks.values()),
        'target_marker_environment':module.ENV, 'downloaded_wheel_bytes':sum(x.get('size_bytes',0) for x in records),
        'installations':0, 'downloaded_code_imported':False, 'runtime_compatibility':'UNVERIFIED; exact offline build and fresh probes require approval',
        'deviation':'Explicit Linux CPython3.13 adaptation. No upstream installer, build hook, dependency resolver or project installation runs. Static tags/closure are not compatibility evidence.'}
    (HERE/'runtime-support-review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pins':[{k:x.get(k) for k in ('project','version','filename','error_type','error')} for x in records],
        'bytes':report['downloaded_wheel_bytes'], 'closure':report['complete_static_dependency_closure'],
        'unsatisfied':[x for x in checks.values() if not x['satisfied']]}))


if __name__ == '__main__':
    main()
