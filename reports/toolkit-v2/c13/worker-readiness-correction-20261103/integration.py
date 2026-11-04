"""Reuse the frozen task/engine helpers with a nonrecursive reviewed skill."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / 'ase-controlled-workflow-20261103'
sys.path.insert(0, str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('frozen_engineering_helpers', OLD / 'run.py')
previous = importlib.util.module_from_spec(spec)
original_import_path = list(sys.path)
try:
    spec.loader.exec_module(previous)
finally:
    sys.path[:] = original_import_path
prepared = previous.prepared

from aeep.assessment.models import content_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep_toolkit.candidate import inspect

TAG = 'aeep-toolkit-v2/stack-check:readiness-20261103'
WORK = ROOT / '.aeep/worker-readiness-correction-20261103'


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def pair(image, source=None):
    source = source or load(HERE / 'context.json')['source']
    original, shared = prepared.pair(image)
    raw = json.loads(original.model_dump_json().replace('aeep-stack-check', 'stack-check'))
    payload = inspect(HERE / 'candidate')
    files = payload.describe()['files']
    primary = '/opt/dependencies/stack-check/SKILL.md'
    package = {'/opt/dependencies/stack-check/' + name: digest for name, digest in files.items()}
    shared.update(source=source, candidate_sha256=payload.sha256,
        purpose='Two selected evaluator engineering checks, nonrecursive neutral fixture; no comparison')
    shared_digest = content_digest(shared)
    raw['candidate_skill_digest'] = files['SKILL.md']
    raw['reviewed_skill']['files'] = package
    raw['treatment']['config']['managed_worker']['reviewed_files'] = {
        **raw['control']['config']['managed_worker']['reviewed_files'], **package}
    raw['treatment']['config']['invocation']['skill_sha256'] = files['SKILL.md']
    common = raw['differential']['control_inventory']
    common['common_profile'] = shared_digest
    candidate = {'skill:stack-check': files['SKILL.md']}
    raw['differential'].update(shared_definition_digest=shared_digest,
        candidate_inventory=candidate, treatment_inventory={**common, **candidate})
    return WorkerPairInspection.model_validate(raw), shared

# Reuse only the immutable task/scheduler helpers. Execution stays in run.py.
inspect = prepared.inspect
recipe = prepared.recipe
scheduler = prepared.scheduler
snapshot = prepared.snapshot
RUNTIME = prepared.RUNTIME
PARENT_TAG = prepared.PARENT_TAG
PARENT_ID = prepared.PARENT_ID
GRADER = prepared.GRADER

TOOLS = prepared.TOOLS
SCHEDULER_WORK = prepared.SCHEDULER_WORK
ASE_REVISION = prepared.ASE_REVISION
ASE_ARTIFACT = prepared.ASE_ARTIFACT
