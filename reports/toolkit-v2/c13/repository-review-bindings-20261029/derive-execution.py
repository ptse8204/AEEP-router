"""Bind only the approved output image and exact selected Git files before calls."""
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import (AssessmentEnvironment, AssessmentScopeAmendment,
    AssessmentSubject, RecipeMaterializationRequest, content_digest)

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
    bundle = json.loads((HERE / 'runtime-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sha(HERE / 'runtime-review.json')
    build = json.loads((HERE / 'build-result.json').read_text())
    assert build['passed'] and build['parent_review_sha256'] == approval['review_sha256']
    assert build['inherited_config_verified'] and build['parent_layers_verified']
    template_path = HERE / 'template-operation-review.json'
    assert sha(template_path) == bundle['template_review_sha256']
    template = json.loads(template_path.read_text())
    parent_path = ROOT / template['parent_review']
    assert sha(parent_path) == template['parent_review_sha256']
    parent = json.loads(parent_path.read_text())
    before = RecipeMaterializationRequest.model_validate(template['request'])
    original = next(v['document'] for v in parent['documents'].values() if v['kind'] == 'environment')
    environment = AssessmentEnvironment.model_validate({**original,
        'environment_id': 'repository-shared-native-runtime-20261028',
        'container_image': build['image_id']})
    env_digest = content_digest(environment)
    parent['documents'] = {k: v for k, v in parent['documents'].items() if v['kind'] != 'environment'}
    parent['documents'][env_digest] = {'kind': 'environment', 'id': environment.environment_id,
        'document': environment.model_dump(mode='json')}
    parent['image'] = build['image_id']
    parent['request']['environment_digest'] = env_digest
    parent['request']['definition_digests'] = [env_digest if k == before.environment_digest else k
        for k in before.definition_digests]
    save(OUT / 'parent-runtime-review.json', parent)
    component = json.loads((HERE / 'component-preparation.json').read_text())
    context = ROOT / bundle['build_context']
    assets = {**template['assets'], **bundle['assets']}
    for name, digest in component['context_files'].items():
        assert sha(context / name) == digest and not (context / name).is_symlink()
        assets[str((context / name).resolve())] = digest
    for path in (HERE / 'build-result.json', HERE / 'component-preparation.json',
                 HERE / 'runtime-review.json', OUT / 'parent-runtime-review.json'):
        assets[str(path.resolve())] = sha(path)
    for path, digest in assets.items():
        assert sha(Path(path)) == digest
    subject = AssessmentSubject(kind='command', location=str((ROOT / template['cases_file']).parent),
        dependency_digests=assets, description='Frozen Dead204 task and exact reviewed Git component in a derived contained image. No models or general Git qualification.')
    request = RecipeMaterializationRequest(schema_version=before.schema_version,
        subject_digest=content_digest(subject), recipe_digest=before.recipe_digest,
        mapping_digest=before.mapping_digest, environment_digest=env_digest,
        authorization_id='onboarding', seed=120,
        definition_digests=parent['request']['definition_digests'],
        runtime_dependencies=before.runtime_dependencies)
    documents = dict(parent['documents'])
    new_docs = {content_digest(v): {'kind': k, 'id': i, 'document': v.model_dump(mode='json')}
        for k, i, v in [('subject', subject.subject_id, subject),
                        ('recipe_materialization_request', request.plan_id, request)]}
    documents.update(new_docs)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding',
        authorization_digest=bundle['authorization_digest'], subject_digests=[content_digest(subject)],
        recipe_digests=[before.recipe_digest], environment_digests=[env_digest], reviewed_digests=list(documents))
    review = {**template, 'assets': assets, 'parent_review': str((OUT / 'parent-runtime-review.json').relative_to(ROOT)),
        'parent_review_sha256': sha(OUT / 'parent-runtime-review.json'),
        'request': request.model_dump(mode='json'), 'new_documents': new_docs,
        'reviewed_document_digests': list(documents), 'amendment': amendment.model_dump(mode='json'),
        'parent_image': build['image_id'], 'maximum_operations': bundle['maximum_operations'],
        'maximum_reserved_seconds': bundle['maximum_reserved_seconds'],
        'derived_directory': '.aeep/repository-shared-native-runtime-20261028/derived',
        'derived_from_approved_bundle': approval['review_sha256'],
        'budget_anchor_includes_the_single_build_and_download_operation': True}
    save(OUT / 'operation-review.json', review)
    save(OUT / 'operator-approval.json', {**approval, 'review_sha256': sha(OUT / 'operation-review.json'),
        'parent_review_sha256': approval['review_sha256'], 'new_human_reply_claimed': False,
        'authority': 'Exact parent approval includes this deterministic image/environment/content binding and finite calls. Programs,source,assertions,reference,faults and permissions do not change.'})
    save(OUT / 'review-budget-anchor.json', json.loads((HERE / 'review-budget-anchor.json').read_text()))
    print(json.dumps({'derived_review_sha256': sha(OUT / 'operation-review.json'),
        'image_id': build['image_id'], 'environment_digest': env_digest,
        'all_programs_and_task_bytes_unchanged': True}))


if __name__ == '__main__':
    main()
