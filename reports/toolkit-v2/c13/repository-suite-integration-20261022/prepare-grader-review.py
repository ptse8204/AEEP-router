"""Bind inert v5 development payloads to one finite offline execution review."""
import base64
import hashlib
import json
from pathlib import Path
import shutil

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentEnvironment, AssessmentScopeAmendment,
    AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest)
from aeep.assessment.repository_suites import RepositorySuiteCase, pack_files
from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep/repository-suite-integration-20261022-v2/protected'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'grader-operation-review.json').exists()
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3
    cases = [RepositorySuiteCase.model_validate(value) for value in json.loads((PRIVATE / 'cases.json').read_text())]
    recipe = RecipeDefinition.model_validate_json((PRIVATE / 'recipe.json').read_text())
    assert recipe.extension.schema_version == 'assessment.recipe-extension.v5'
    assert len(cases) == 3 and all(case.split == 'development' and case.used_for_development for case in cases)
    preparation = json.loads((HERE / 'development-assets-preparation.json').read_text())
    assert preparation['prepared'] and not preparation['external_code_executed']
    assert sha(PRIVATE / 'cases.json') == preparation['cases_file_sha256']
    assert sha(PRIVATE / 'recipe.json') == preparation['recipe_sha256']
    canary = '.aeep/repository-suite-integration-20261022-v2/host-only-canary'
    state = '/tmp/aeep-suite-development-state-20261022'
    boundary = '''import os,socket
from pathlib import Path

def test_boundary():
    assert os.getuid() == 65534
    p = Path(CANARY)
    try:
        p.read_bytes()
    except (PermissionError, FileNotFoundError):
        pass
    else:
        raise AssertionError('host canary visible')
    try:
        Path('/aeep-boundary-write').write_text('forbidden')
    except (PermissionError, OSError):
        pass
    else:
        raise AssertionError('root filesystem writable')
    sock = socket.socket()
    sock.settimeout(.3)
    try:
        sock.connect(('1.1.1.1', 53))
    except OSError:
        pass
    else:
        raise AssertionError('unexpected general network')
    finally:
        sock.close()
'''.replace('CANARY', repr(str(ROOT / canary)))
    programs = {'boundary': boundary,
        'state_write': 'from pathlib import Path\ndef test_state():\n    p=Path(' + repr(state) + ')\n    assert not p.exists()\n    p.write_text("owned synthetic state")\n',
        'state_read': 'from pathlib import Path\ndef test_state():\n    assert not Path(' + repr(state) + ').exists()\n'}
    # The same fixed v5 observer runs these authored boundary tests and real suites.
    wheel_payloads = [{'filename': Path(asset.path).name, 'sha256': asset.sha256,
        'data': base64.b64encode(asset.read()).decode()} for asset in cases[0].truth.wheels]
    probes = []
    for name, program in programs.items():
        archive = pack_files({'tests/test_boundary.py': program.encode()})
        payload = {'archive': base64.b64encode(archive).decode(), 'archive_sha256': hashlib.sha256(archive).hexdigest(),
            'python': '3.13', 'pytest': '8.3.5', 'test_paths': ['tests/test_boundary.py'], 'wheels': wheel_payloads}
        path = PRIVATE / (name + '-payload.json')
        with path.open('x') as stream:
            json.dump(payload, stream, separators=(',', ':'))
        probes.append({'name': name, 'payload': str(path.relative_to(ROOT)), 'payload_sha256': sha(path),
            'payload_bytes': path.stat().st_size, 'archive_sha256': payload['archive_sha256'],
            'expected_node': 'tests/test_boundary.py::' + ('test_boundary' if name == 'boundary' else 'test_state')})
    environment = AssessmentEnvironment(environment_id='repository-suite-development-20261022', kind='container', identity={},
        container_image='sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',
        container_runtime='/usr/local/bin/docker', container_socket='/Users/edwintse/.docker/run/docker.sock', network=False)
    assets = {str(path): sha(path) for path in (PRIVATE / 'cases.json', PRIVATE / 'recipe.json')}
    for case in cases:
        for asset in (case.truth.source, case.truth.tests, case.reference, *case.truth.wheels):
            asset.read()
            assets[asset.path] = asset.sha256
    variants = preparation['staged_payloads']
    for item in variants:
        assert sha(ROOT / item['payload']) == item['sha256']
        assets[str(ROOT / item['payload'])] = item['sha256']
    for item in probes:
        assets[str(ROOT / item['payload'])] = item['payload_sha256']
    subject = AssessmentSubject(kind='command', location=str(PRIVATE), dependency_digests=assets,
        description='Three source-only real upstream development cases and synthetic containment probes; no model task.')
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
    request = RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
        subject_digest=content_digest(subject), recipe_digest=content_digest(recipe), mapping_digest=content_digest(recipe),
        environment_digest=content_digest(environment), authorization_id='onboarding', seed=31,
        definition_digests=[content_digest(recipe), content_digest(environment), content_digest(runtime)], runtime_dependencies=runtime.dependencies)
    documents = {}
    for kind, identity, value in [('subject', subject.subject_id, subject), ('recipe', recipe.recipe_id, recipe),
        ('environment', environment.environment_id, environment), ('recipe_runtime', content_digest(runtime), runtime),
        ('recipe_materialization_request', request.plan_id, request)]:
        documents[content_digest(value)] = {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
    auth = '7cf37077213dd84d02ffb6c8c1106930ecec04d4337780454f6ac308b0bef659'
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=auth,
        subject_digests=[content_digest(subject)], recipe_digests=[content_digest(recipe)],
        environment_digests=[content_digest(environment)], reviewed_digests=list(documents))
    review = {'purpose': 'One fresh v5 development conformance attempt, not qualification or comparative usefulness.',
        'source_digest': verification_source_digest(ROOT), 'runner_sha256': sha(HERE / 'run-grader-review.py'),
        'cases_file': str((PRIVATE / 'cases.json').relative_to(ROOT)), 'cases_file_sha256': sha(PRIVATE / 'cases.json'),
        'assets': assets, 'probes': probes, 'variants': variants, 'request': request.model_dump(mode='json'),
        'recipe': recipe.model_dump(mode='json'), 'documents': documents,
        'definitions': {key: item['document'] for key, item in documents.items()}, 'amendment': amendment.model_dump(mode='json'),
        'authorization_digest': auth, 'image': environment.container_image, 'docker': environment.container_runtime,
        'socket': 'unix://' + environment.container_socket, 'host_canary': canary,
        'maximum_contained_calls': 12, 'maximum_operations': 14, 'maximum_reserved_seconds': 630,
        'maximum_model_turns': 0, 'cash_usd': 0, 'network': False, 'automatic_retry': False,
        'runtime_versions': {'python':'3.13','pytest':'8.3.5'},
        'development_exclusion': [case.independent_case_id for case in cases] + ['pgmpy__pgmpy-3137'],
        'effects': ['Run three synthetic containment/state probes and nine real repository observations through the unchanged v5 observer in twelve fresh offline containers.',
            'Load 7/8/9 exact cached pure-Python wheels with zipimport; no installer or build backend. Click and Marshmallow wheels supply distribution metadata, while reviewed source/src precedes wheel code.',
            'Reference repairs must pass every required test. Unchanged source must fail bug tests and preserve existing tests. Validly scoped semantic faults must not pass. Missing/error statuses cannot become a pass.',
            'Record exact finite scope amendment under standing delegation; preserve all canonical counters. Remove only attempt-owned containers and the unchanged synthetic host canary.',
            'No downloads, image pulls/builds, model workers, credentials, new destinations, paid services, activation, publication, retained images, volumes, backups or unrelated cleanup.'],
        'limitations': ['Three inspected issues are development-only, all single-file Python repairs. They are not the 8/28/105 assessment corpus and establish no model or selection improvement.',
            'Published documentation/release-note changes are explicitly outside this source-only adaptation. Marshmallow Python3.11 is adapted to3.13. This is not the official upstream image or benchmark score.',
            'Required test completeness and log forgery remain review limitations; the grader does not prove arbitrary preservation or adversarial test integrity.'],
        'approval_reason': 'The pasted continuation excludes untrusted software execution. CONTINUATION.md requires applicable new contained-execution authority; completed review56ca1751 covers an older one-case prototype only.'}
    with (HERE / 'grader-operation-review.json').open('x') as stream:
        json.dump(review, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'review_sha256': sha(HERE / 'grader-operation-review.json'), 'operations': 14, 'calls': 12,
        'source_digest': review['source_digest'], 'execution_started': False}))


if __name__ == '__main__':
    main()
