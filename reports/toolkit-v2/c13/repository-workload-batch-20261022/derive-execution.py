"""Derive only the approved image-bound environment and finite execution review."""
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import (AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject,
    RecipeMaterializationRequest, content_digest)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE / 'runtime-execution'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    bundle = json.loads((HERE / 'approval-bundle.json').read_text())
    approved = json.loads((HERE / 'operator-approval.json').read_text())
    assert approved['approved'] and approved['review_sha256'] == sha(HERE / 'approval-bundle.json')
    build = json.loads((HERE / 'build-result.json').read_text())
    assert build['passed'] and build['parent_review_sha256'] == approved['review_sha256']
    parent_path = ROOT / bundle['parent_review']
    assert sha(parent_path) == bundle['parent_review_sha256']
    parent = json.loads(parent_path.read_text())
    before = RecipeMaterializationRequest.model_validate(parent['request'])
    old_environment = next(item['document'] for item in parent['documents'].values() if item['kind'] == 'environment')
    environment = AssessmentEnvironment.model_validate({**old_environment,
        'environment_id': 'repository-pydantic-django-runtime-20261022', 'container_image': build['image_id']})
    env_digest = content_digest(environment)
    parent['documents'] = {key: item for key, item in parent['documents'].items() if item['kind'] != 'environment'}
    parent['documents'][env_digest] = {'kind': 'environment', 'id': environment.environment_id,
                                      'document': environment.model_dump(mode='json')}
    parent['image'] = build['image_id']
    parent['request']['environment_digest'] = env_digest
    parent['request']['definition_digests'] = [env_digest if key == before.environment_digest else key
                                              for key in before.definition_digests]
    save(OUT / 'parent-runtime-review.json', parent)
    subject = AssessmentSubject(kind='command', location=str((ROOT / bundle['cases_file']).parent),
        dependency_digests=bundle['assets'], description='Twenty-two provisional tasks and three fresh runtime probes; no campaign or models.')
    request = RecipeMaterializationRequest(schema_version=before.schema_version, subject_digest=content_digest(subject),
        recipe_digest=before.recipe_digest, mapping_digest=before.mapping_digest, environment_digest=env_digest,
        authorization_id=before.authorization_id, seed=67, definition_digests=parent['request']['definition_digests'],
        runtime_dependencies=before.runtime_dependencies)
    documents = {key: item for key, item in parent['documents'].items()
                 if item['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    new_docs = {content_digest(value): {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
        for kind, identity, value in [('subject', subject.subject_id, subject),
            ('recipe_materialization_request', request.plan_id, request)]}
    documents.update(new_docs)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=bundle['authorization_digest'],
        subject_digests=[content_digest(subject)], recipe_digests=[before.recipe_digest], environment_digests=[env_digest],
        reviewed_digests=list(documents))
    derived = {key: bundle[key] for key in ('source_digest', 'authorization_digest', 'assets', 'cases_file',
        'variants_file', 'active_case_ids', 'expectations', 'variant_labels')}
    derived.update(parent_review=str((OUT / 'parent-runtime-review.json').relative_to(ROOT)),
        parent_review_sha256=sha(OUT / 'parent-runtime-review.json'),
        driver_files={name: sha(OUT / name) for name in ('run.py', 'classify.py', 'audit-execution.py')}, request=request.model_dump(mode='json'),
        new_documents=new_docs, reviewed_document_digests=list(documents), amendment=amendment.model_dump(mode='json'),
        maximum_operations=bundle['maximum_operations'] - 1, maximum_reserved_seconds=bundle['maximum_reserved_seconds'] - 180, maximum_contained_calls=bundle['maximum_contained_calls'],
        probes=parent['probes'], derived_from_approved_bundle=approved['review_sha256'],
        build_result_sha256=sha(HERE / 'build-result.json'))
    save(OUT / 'operation-review.json', derived)
    save(OUT / 'operator-approval.json', {**approved, 'review_sha256': sha(OUT / 'operation-review.json'),
        'parent_review_sha256': approved['review_sha256'],
        'authority': 'Parent bundle approval explicitly covers this deterministic image/environment derivation and at most ninety-seven offline calls. This is not a separate human response or general execution authority.'})
    print(json.dumps({'derived_review_sha256': sha(OUT / 'operation-review.json'), 'image_id': build['image_id'],
                      'environment_digest': env_digest, 'maximum_calls': bundle['maximum_contained_calls']}))


if __name__ == '__main__':
    main()
