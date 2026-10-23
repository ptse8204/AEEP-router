"""Construct new compact-case definitions, not inherited runtime qualification."""
import hashlib
import json
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentSubject, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAsset, SuiteTruthV3, compressed_patch_artifact, decode_patch, repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.aeep/repository-compact-patches-20261022-envelope'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    prior = HERE.parent / 'repository-replacement-runtime-20261022/runtime-execution/parent-runtime-review.json'
    old = json.loads(prior.read_text())
    cases = [RepositorySuiteCase.model_validate(x) for x in json.loads((ROOT / '.aeep/repository-suite-integration-20261022-v2/protected/cases.json').read_text())]
    converted = []
    for case in cases:
        data = case.model_dump(mode='json')
        data['schema_version'] = 'assessment.repository-suite-case.v3'
        data['truth'] = SuiteTruthV3(**case.truth.model_dump(), patch_encoding='gzip-json').model_dump(mode='json')
        ref = OUT / (case.input.task_id + '-reference.json')
        ref.write_text(json.dumps(compressed_patch_artifact(decode_patch(json.loads(case.reference.read()))), separators=(',', ':')))
        data['reference'] = SuiteAsset(path=str(ref.resolve()), sha256=sha(ref), size_bytes=ref.stat().st_size).model_dump(mode='json')
        data['fault_outputs'] = [compressed_patch_artifact(decode_patch(x)) for x in case.fault_outputs]
        data['provenance'] += ' Separate v3 compressed-output development definition; source/assertions unchanged, old conformance is not transferred.'
        converted.append(RepositorySuiteCase.model_validate(data))
    recipe = repository_suite_recipe(converted)
    path = OUT / 'recipe.json'
    path.write_text(recipe.model_dump_json(indent=2) + '\n')
    old_request = RecipeMaterializationRequest.model_validate(old['request'])
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
    environment_entry = next(x for x in old['documents'].values() if x['kind'] == 'environment')
    environment = environment_entry['document']
    subject = AssessmentSubject(kind='command', location=str(OUT), dependency_digests={str(path.resolve()): sha(path)}, description='New v3 compact-output development recipe envelope; no candidate cases adopted or executed.')
    request = RecipeMaterializationRequest(schema_version=old_request.schema_version, subject_digest=content_digest(subject), recipe_digest=content_digest(recipe), mapping_digest=content_digest(recipe),
        environment_digest=old_request.environment_digest, authorization_id='onboarding', seed=59,
        definition_digests=[content_digest(recipe), old_request.environment_digest, content_digest(runtime)], runtime_dependencies=runtime.dependencies)
    documents = {old_request.environment_digest: environment_entry}
    documents.update({content_digest(value): {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')} for kind, identity, value in [('recipe', recipe.recipe_id, recipe), ('recipe_runtime', content_digest(runtime), runtime), ('subject', subject.subject_id, subject), ('recipe_materialization_request', request.plan_id, request)]})
    result = {'source_digest': verification_source_digest(ROOT), 'prior_definition_only': str(prior.relative_to(ROOT)), 'prior_review_sha256': sha(prior),
        'recipe': recipe.model_dump(mode='json'), 'request': request.model_dump(mode='json'), 'documents': documents,
        'authorization_digest': old['authorization_digest'], 'image': old['image'], 'docker': old['docker'], 'socket': old['socket'],
        'host_canary': old['host_canary'], 'probes': old['probes'], 'external_execution': False, 'old_conformance_applies_to_new_source': False,
        'fresh_boundary_state_runtime_probes_required': 3, 'observer_program_unchanged': recipe.dependencies['program'] == old['recipe']['dependencies']['program']}
    (HERE / 'parent-runtime-review.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'new_recipe_id': recipe.recipe_id, 'recipe_digest': content_digest(recipe), 'source_digest': result['source_digest'], 'fresh_probes': len(result['probes']), 'image_unchanged': result['image']}))


if __name__ == '__main__':
    main()
