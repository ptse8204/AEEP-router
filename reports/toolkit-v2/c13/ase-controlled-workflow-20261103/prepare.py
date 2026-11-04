"""Prepare exact engineering inputs. Never start upstream code, Docker or models."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.assessment.scheduling import SchedulerDefinition
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import ExecutorSpec
from aeep_toolkit.ase_contract import ASE_ARTIFACT, ASE_REVISION, ASE_SOURCE_FILES
from aeep_toolkit.candidate import inspect
from aeep_toolkit.install_runtime import snapshot
from aeep_toolkit.models import SourcePin

PARENT_TAG = 'aeep-toolkit-v2/capture-policy-local-tag-20261021:control'
PARENT_ID = 'sha256:0c05b495931e8558baf76b099c01c3b80a4b5136b5640d387db2d8ee644cf1db'
TAG = 'aeep-toolkit-v2/ase-stack-check:reviewed-20261103'
GRADER = 'sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04'
RUNTIME = ROOT / '.aeep/upstream-stack-runtimes-20261102/corrected-composed-runtime'
WORK = ROOT / '.aeep/ase-controlled-workflow-20261103'
TOOLS = WORK / 'tools'
SCHEDULER_WORK = WORK / 'scheduler'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def recipe():
    from aeep.assessment.repository_suites import RepositorySuiteCase, repository_suite_recipe
    raw = load(HERE / 'recipe-base.json')
    # Keep three already-reviewed independent literals for the established grader
    # contract; only task.json becomes a model task. No new corpus is added.
    literals = [RepositorySuiteCase.model_validate(case) for case in raw['generator_config']['cases'][:3]]
    rec = repository_suite_recipe(literals)
    rec.recipe_id = 'ase-controlled-engineering-20261103'
    rec.description = 'One public model task plus three existing protected calibration cases; integration only'
    rec.dependencies['benchmark_pack'] = content_digest({
        'kind': 'existing-public-repository-engineering-task',
        'case': load(HERE / 'task.json'),
        'calibration_cases': [case.model_dump(mode='json') for case in literals],
    })
    return RecipeDefinition.model_validate(rec.model_dump(mode='json'))



def pair(image):
    raw = load(HERE / 'pair-base.json')
    rec = recipe()
    payload = inspect(HERE / 'candidate')
    skill = payload.describe()['files']['SKILL.md']
    shared = {
        'purpose': 'Required-use stack engineering; two independently selected engines, no comparison',
        'recipe': content_digest(rec), 'source': load(HERE / 'context.json')['source'],
        'previous_shared_definition': raw['differential']['shared_definition_digest'],
    }
    shared_ref = content_digest(shared)
    raw.update(schema_version='assessment.worker-pair-inspection.v4', profile='reviewed-skill:1',
               candidate_skill_digest=skill,
               reviewed_skill={
                   'primary_path': '/opt/dependencies/aeep-stack-check/SKILL.md',
                   'alias_path': '/etc/codex/skills/aeep-stack-check/SKILL.md',
                   'package_root': '/opt/dependencies/aeep-stack-check',
                   'aliases': ['aeep-stack-check'],
                   'files': {'/opt/dependencies/aeep-stack-check/' + name: digest
                             for name, digest in payload.describe()['files'].items()},
               })
    diff = raw['differential']
    common = {k: v for k, v in diff['control_inventory'].items() if k != 'common_profile'}
    common['common_profile'] = shared_ref
    diff.update(shared_definition_digest=shared_ref, control_inventory=common,
                candidate_inventory={'aeep_stack_check_skill': skill},
                treatment_inventory={**common, 'aeep_stack_check_skill': skill},
                candidate_paths=['/opt/dependencies/aeep-stack-check/SKILL.md',
                                 '/etc/codex/skills/aeep-stack-check/SKILL.md',
                                 '/opt/dependencies/aeep-stack-check'],
                candidate_aliases=['aeep-stack-check'])
    for role in ('control', 'treatment'):
        spec = raw[role]
        spec['id'] = 'toolkit-ase-stack-20261103.' + role
        spec.update(capability=rec.capability, input_schema=rec.input_schema, output_schema=rec.output_schema)
        cfg = spec['config']
        cfg['adapter_id'] = 'codex-app-server:aeep-stack-' + role + '-20261103'
        cfg['managed_worker']['worker_id'] = 'aeep-stack-' + role + '-20261103'
        # Both identities retain the same reviewed protected credential mechanism.
        # Never inspect or copy its volume contents.
        if role == 'treatment':
            cfg['managed_worker']['image'] = image
            cfg['managed_worker']['reviewed_files'] = {
                **raw['control']['config']['managed_worker']['reviewed_files'],
                **raw['reviewed_skill']['files'],
            }
            cfg['invocation'].update(mode='skill', skill_name='aeep-stack-check',
                                     skill_path='/opt/dependencies/aeep-stack-check/SKILL.md',
                                     skill_sha256=skill, exposure='required')
        public_root = str(Path(load(HERE / 'task.json')['truth']['source']['path']).parent)
        cfg['assessment_adapter']['read_only_roots'] = [public_root]
        cfg['artifact']['output_field'] = 'patch_b64'
        cfg['artifact']['output_name'] = 'patch.json'
        cfg['instructions'] = cfg['instructions'].replace('gzip-compressed UTF-8 JSON', 'UTF-8 JSON')
        cfg['instructions'] = cfg['instructions'].replace('Use optional capabilities only when useful.',
            'This is a required skill-loading integration check; follow the reviewed selected skill when supplied.')
    return WorkerPairInspection.model_validate(raw), shared


def scheduler():
    profile = HERE / 'scheduler.sb'
    site = RUNTIME / 'lib/python3.13/site-packages'
    git = Path('/Applications/Xcode.app/Contents/Developer/usr/bin/git')
    deps = {str(p): sha(p) for p in [profile, TOOLS / 'git', git,
            Path('/usr/bin/sandbox-exec'), Path(sys.executable).resolve(),
            site / 'aeep_toolkit/ase_child.py', site / 'aeep_toolkit/ase_contract.py']}
    deps.update({str(site / name): expected for name, expected in ASE_SOURCE_FILES.items()})
    return SchedulerDefinition(
        adapter_id='agent-skill-eval.controlled.v1', source_revision=ASE_REVISION,
        artifact_sha256=ASE_ARTIFACT, executable_dependencies=deps,
        workspace=str(SCHEDULER_WORK), runtime_root=str(RUNTIME), runtime_tree_digest=snapshot(RUNTIME),
        boundary_profile=str(profile), overhead_seconds=60, maximum_requests=1,
        executor=ExecutorSpec(id='ase.real-controlled-stack', capability='assessment.scheduler@1',
            kind='command', description='Actual pinned ASE scheduler over one canonical controlled trial',
            side_effect='write', config={
                'argv': ['/usr/bin/sandbox-exec', '-f', str(profile), str(RUNTIME / 'bin/python'),
                         '-I', '-B', '-m', 'aeep_toolkit.ase_child'],
                'argv_literal': True, 'inherit_env': False, 'stdin_json': True,
                'cwd': str(SCHEDULER_WORK), 'env': {
                    'PATH': str(TOOLS) + ':/usr/bin:/bin', 'HOME': str(SCHEDULER_WORK / 'home'),
                    'TMPDIR': str(SCHEDULER_WORK / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1',
                    'PYTHONNOUSERSITE': '1', 'LC_ALL': 'C'},
                'timeout_seconds': 600, 'max_output_bytes': 65536,
                'output': {'type': 'jsonl', 'match': {'kind': 'done'}},
            }))


def main():
    from aeep.assessment.verification import verification_source_digest

    assert not (HERE / 'context.json').exists()
    WORK.mkdir(mode=0o700)
    TOOLS.mkdir(mode=0o700)
    old = HERE.parent / 'next-stack-integration-audit-20261103/ase-git-wrapper.py'
    text = old.read_text().replace(
        '/Users/edwintse/Documents/aeep-toolkit-v2/.aeep/ase-engineering-work-20261103/scheduler',
        str(SCHEDULER_WORK))
    (TOOLS / 'git').write_text(text)
    (TOOLS / 'git').chmod(0o500)
    spec = importlib.util.spec_from_file_location('existing_native_profile',
        HERE.parent / 'ase-runtime-contract-20261103/native-profile.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (HERE / 'scheduler.sb').write_text(module.profile(RUNTIME, TOOLS, SCHEDULER_WORK, HERE / 'native-check.py'))
    context = load(HERE.parent / 'ase-runtime-contract-20261103/context.json')
    source = verification_source_digest(ROOT)
    assert source == context['source']
    site = RUNTIME / 'lib/python3.13/site-packages'
    for name, digest in ASE_SOURCE_FILES.items():
        assert sha(site / name) == digest
    for name in ('ase_child.py', 'ase_contract.py'):
        assert sha(site / 'aeep_toolkit' / name) == sha(ROOT / 'src/aeep_toolkit' / name)
    candidate_commit = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        str(HERE / 'candidate')], text=True).strip()
    source_pin = SourcePin(repository='https://github.com/ptse8204/AEEP-router',
        revision=candidate_commit, artifact_sha256=inspect(HERE / 'candidate').sha256,
        license_expression='Apache-2.0',
        data_rights='Repository-authored engineering fixture; no demonstrated usefulness')
    write(HERE / 'source.json', source_pin.model_dump(mode='json'))
    write(HERE / 'context.json', {'source': source, 'runtime': str(RUNTIME),
        'runtime_tree_sha256': snapshot(RUNTIME), 'candidate': inspect(HERE / 'candidate').describe(),
        'candidate_commit': candidate_commit, 'parent_tag': PARENT_TAG, 'parent_id': PARENT_ID,
        'output_tag': TAG, 'grader': GRADER, 'work': str(WORK),
        'controlled_workers_or_upstream_executed': False})
    write(HERE / 'recipe.json', recipe().model_dump(mode='json'))
    write(HERE / 'scheduler.json', scheduler().model_dump(mode='json'))
    # A distinct explicit placeholder is a schema fixture, never a measured image.
    paired, shared = pair('sha256:' + 'e' * 64)
    write(HERE / 'pair-shape-fixture.json', paired.model_dump(mode='json'))
    write(HERE / 'shared-definition.json', shared)
    print(json.dumps({'prepared': True, 'source': source, 'candidate_commit': candidate_commit,
                      'image_built': False, 'models': 0, 'upstream_imports': 0}))


if __name__ == '__main__':
    main()
