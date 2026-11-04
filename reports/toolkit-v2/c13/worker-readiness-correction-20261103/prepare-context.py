"""Prepare exact local files and fixture metadata, never upstream execution."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import integration as prepared
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.models import SourcePin

HERE, ROOT = prepared.HERE, prepared.ROOT
source = verification_source_digest(ROOT)
assert not (HERE / 'context.json').exists()
assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
prepared.WORK.mkdir(mode=0o700)
context = prepared.WORK / 'build-context'
context.mkdir(mode=0o700)
(context / 'candidate').mkdir(mode=0o700)
for name in ('Dockerfile', 'candidate/SKILL.md', 'candidate/LICENSE'):
    shutil.copyfile(HERE / name, context / name)
assert not prepared.prepared.SCHEDULER_WORK.exists()
payload = prepared.inspect(HERE / 'candidate')
revision = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--', str(HERE / 'candidate')], text=True).strip()
assert revision
pin = SourcePin(repository='https://github.com/ptse8204/AEEP-router', revision=revision,
    artifact_sha256=payload.sha256, license_expression='Apache-2.0',
    data_rights='Repository-authored nonrecursive engineering fixture; no usefulness established')
prepared.write(HERE / 'source.json', pin.model_dump(mode='json'))
prepared.write(HERE / 'context.json', {'source': source, 'candidate': payload.describe(),
    'candidate_commit': revision, 'runtime_tree_sha256': prepared.snapshot(prepared.RUNTIME),
    'runtime_scope': 'Unchanged ASE child and contract only; other installed AEEP modules retain prior scope',
    'controlled_workers_or_upstream_executed': False, 'actual_models': 0})
pair, shared = prepared.pair('sha256:' + 'e' * 64, source)
prepared.write(HERE / 'pair-shape-fixture.json', pair.model_dump(mode='json'))
prepared.write(HERE / 'shared-definition.json', shared)
# The existing recording fixture inspects actual rendered instructions only.
spec = importlib.util.spec_from_file_location('recorded_task_delivery', prepared.OLD / 'check-task-delivery.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE = HERE
import asyncio
asyncio.run(module.main())
print(json.dumps({'prepared': True, 'candidate_revision': revision, 'source': source,
    'builds_models_upstream_or_grant_mutations': 0}))
