"""Inert controller guards; no untrusted executable or real grant operation."""
import asyncio
import copy
import importlib.util
import json
import sys

import integration as prepare
import run

checks = []
parent = {'Id': prepare.PARENT_ID, 'Layers': ['a', 'b'], 'Size': 100,
          'User': '65534:65534', 'Workdir': '/workspace', 'Entrypoint': ['/bin/true']}
image = {**parent, 'Id': 'sha256:' + 'a' * 64, 'Layers': ['a', 'b', 'x', 'y', 'z', 'r', 's'], 'Size': 110}
run.require_image({'parent_metadata': parent}, image)
checks.append('exact parent plus five reviewed filesystem layers accepted')
for name, value in (
    ('parent-image', {**image, 'Id': parent['Id']}),
    ('missing-layer', {**image, 'Layers': ['a', 'b', 'x']}),
    ('changed-parent', {**image, 'Layers': ['a', 'c', 'x', 'y', 'z', 'r', 's']}),
    ('changed-user', {**image, 'User': '0:0'}),
    ('changed-entrypoint', {**image, 'Entrypoint': ['/bin/sh']}),
    ('oversize-layer', {**image, 'Size': 4 * 1024**2}),
):
    try:
        run.require_image({'parent_metadata': parent}, value)
    except RuntimeError:
        checks.append(name + ' rejected')
    else:
        raise AssertionError(name)
try:
    run.require_assets({'source_digest': '0' * 64})
except RuntimeError:
    checks.append('source drift stops before any Docker operation')
else:
    raise AssertionError('source drift accepted')
spec = importlib.util.spec_from_file_location('reviewed_budget_controls',
    prepare.HERE.parent / 'repository-usefulness-pilot-20261029/review-budget.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.self_check() == 7
checks.append('seven existing finite budget controls pass')
sys.argv = ['run.py', 'invalid-digest']
try:
    asyncio.run(run.main())
except (RuntimeError, FileNotFoundError):
    checks.append('missing exact review refuses dispatch')
else:
    raise AssertionError('missing review accepted')
prepare.write(prepare.HERE / 'controller-controls.json', {
    'passed': True, 'checks': checks, 'first_party_inert_controls_only': True,
    'models': 0, 'worker_or_service_operations': 0, 'grant_mutations': 0})
print(json.dumps({'passed': True, 'controller_checks': len(checks), 'models': 0}))
