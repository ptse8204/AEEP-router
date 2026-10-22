"""Prepare inert exact grader definitions; never launch a worker or change a grant."""
import hashlib
import json
import shutil
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository_tasks import RepositoryCase, repository_recipe
from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'grader-operation-review.json').exists()
    validation = json.loads((HERE / 'validation-v2/source-stability.json').read_text())
    assert validation['all_passed'] and validation['source_digest'] == verification_source_digest(ROOT)
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    path = ROOT / 'examples/repository_evaluation/development-cases.json'
    cases = [RepositoryCase.model_validate(value) for value in json.loads(path.read_text())]
    recipe = repository_recipe(cases)
    recipe.recipe_id += '-development-' + recipe.generator_config['case_set_sha256'][:12]
    subject = AssessmentSubject(kind='command', location=str(path), dependency_digests={str(path): sha(path)},
        description='Pinned first-party repository development fixtures; grader conformance only.')
    environment = AssessmentEnvironment(environment_id='repository-grader-audit-correction-20261021', kind='container',
        identity={}, container_image='sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',
        container_runtime='/usr/local/bin/docker', container_socket='/Users/edwintse/.docker/run/docker.sock',
        network=False)
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
    request = RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
        subject_digest=content_digest(subject), recipe_digest=content_digest(recipe), mapping_digest=content_digest(recipe),
        environment_digest=content_digest(environment), authorization_id='onboarding', seed=29,
        definition_digests=[content_digest(recipe), content_digest(environment), content_digest(runtime)],
        runtime_dependencies=runtime.dependencies)
    documents = {}
    for kind, identity, value in [('subject', subject.subject_id, subject), ('recipe', recipe.recipe_id, recipe),
        ('environment', environment.environment_id, environment), ('recipe_runtime', content_digest(runtime), runtime),
        ('recipe_materialization_request', request.plan_id, request)]:
        documents[content_digest(value)] = {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
    auth = '7cf37077213dd84d02ffb6c8c1106930ecec04d4337780454f6ac308b0bef659'
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=auth,
        subject_digests=[content_digest(subject)], recipe_digests=[content_digest(recipe)],
        environment_digests=[content_digest(environment)], reviewed_digests=list(documents))
    canary = '.aeep/repository-audit-correction-20261021/host-only-canary.txt'
    boundary = '''import os, pathlib, socket
def containment():
    try:
        pathlib.Path(HOST_CANARY).read_text()
        host_visible = True
    except OSError:
        host_visible = False
    try:
        pathlib.Path('/etc/aeep-repository-canary').write_text('fixture')
        root_write = True
    except OSError:
        root_write = False
    try:
        connection = socket.create_connection(('192.0.2.1', 9), timeout=.2)
        connection.close()
        network = True
    except OSError:
        network = False
    return {'host_visible': host_visible, 'root_write': root_write, 'network': network, 'uid': os.getuid()}
def state(write):
    path = pathlib.Path('/tmp/aeep-repository-freshness-canary')
    before = path.exists()
    if write:
        path.write_text('fixture')
    return before
'''.replace('HOST_CANARY', repr(str(ROOT / canary)))
    probes = []
    for name, call, args, expected in [('containment', 'containment', [],
        dict(host_visible=False, root_write=False, network=False, uid=65534)),
        ('state_write', 'state', [True], False), ('state_fresh', 'state', [False], False)]:
        probes.append({'name': name, 'payload': {'files': {'boundary.py': boundary},
            'probe': {'module': 'boundary.py', 'call': call, 'args': args}},
            'expected': {'status': 'ok', 'result': expected}})
    review = {'purpose': 'One source-bound, offline, no-model repository grader conformance check; not qualification or efficacy.',
        'source_digest': validation['source_digest'], 'runner_sha256': sha(HERE / 'run-grader-review.py'),
        'inputs': {'examples/repository_evaluation/development-cases.json': sha(path)},
        'cases': 'examples/repository_evaluation/development-cases.json', 'image': environment.container_image,
        'docker': environment.container_runtime, 'socket': 'unix://' + environment.container_socket,
        'authorization_digest': auth, 'documents': documents,
        'definitions': {key: value['document'] for key, value in documents.items()},
        'request': request.model_dump(mode='json'), 'recipe': recipe.model_dump(mode='json'),
        'amendment': amendment.model_dump(mode='json'), 'boundary_probes': probes,
        'host_canary': canary, 'host_canary_text': 'AEEP reviewed repository grader synthetic host-only canary.\n',
        'maximum_contained_calls': 23, 'maximum_assessment_operations': 25, 'maximum_reserved_seconds': 1240,
        'maximum_model_turns': 0, 'cash_usd': 0, 'network': False,
        'effects': ['Reuse the exact existing runtime image; no builds, pulls, installs, persistent volumes, model proxy or credentials.',
            'Run three containment/freshness observations and twenty fixed behavioral probes through existing canonical reservations and fresh offline containers.',
            'Check three reference patches, three unchanged-snapshot artifacts and three invalid-scope outputs and three validly scoped semantic faults; expected correctness remains in the coordinator.',
            'Count setup, all probes, parent grading/cleanup inspection and reporting overhead separately without double counting child elapsed time. Record exact scope amendment under existing delegation; preserve onboarding grant counters. A source or environment change stops execution.',
            'Create one owned host-only synthetic canary; remove it only if created by this attempt and unchanged. Existing ContainerExecutor removes only attempt-owned containers.'],
        'automatic_retry': False, 'execution_started': False,
        'approval_reason': 'The pasted continuation excludes untrusted software execution and CONTINUATION.md requires applicable container-provisioning authority. Previous bundles are terminal and bind older source. This exact review authorizes no new candidate study, qualification, admission, deployment or historical replay.'}
    (HERE / 'grader-operation-review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({'review_sha256': sha(HERE / 'grader-operation-review.json'), 'execution_started': False}))


if __name__ == '__main__':
    main()
