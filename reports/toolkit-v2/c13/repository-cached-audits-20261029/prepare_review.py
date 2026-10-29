"""Freeze two new authored source audits; no third-party code executes here."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, AssessmentScopeAmendment, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase
from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'repository-cached-git-20261029/runtime-execution'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    assert prepared['prepared_cases'] == 2 and not prepared['errors'] and not prepared['external_code_executed']
    source = verification_source_digest(ROOT)
    previous = json.loads((OLD / 'operation-review.json').read_text())
    assert source == previous['source_digest']
    old_parent = json.loads((ROOT / previous['parent_review']).read_text())
    audit = json.loads((OLD / 'completion-audit.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['canonical_receipts_reopened'] == 19
    values = json.loads((ROOT / prepared['cases_file']).read_text())
    cases = [RepositorySuiteCase.model_validate(value) for value in values]
    core = {wheel.sha256 for wheel in cases[0].truth.wheels}
    assert len(core) == 4 and all({w.sha256 for w in c.truth.wheels} == core for c in cases)
    seed = json.loads((ROOT / previous['cases_file']).read_text())[0]
    assert core <= {w['sha256'] for w in seed['truth']['wheels']}
    recipe_data = json.loads(json.dumps(old_parent['recipe']))
    recipe_data['recipe_id'] = 'repository-cached-source-audits-' + source[:16]
    recipe_data['generator_config']['cases'] = values
    recipe_data['generator_config']['assessment'] = False
    recipe_data['generator_config']['provisional_source_only'] = True
    recipe = RecipeDefinition.model_validate(recipe_data)
    for role in ('reference', 'grader'):
        assert recipe.model_dump(mode='json')['extension'][role] == old_parent['recipe']['extension'][role]
    documents = {k: v for k, v in old_parent['documents'].items() if v['kind'] in ('environment', 'recipe_runtime')}
    documents[content_digest(recipe)] = {'kind': 'recipe', 'id': recipe.recipe_id, 'document': recipe.model_dump(mode='json')}
    canary = '.aeep/repository-cached-audit-execution-20261029/host-canary'
    private = ROOT / '.aeep/repository-cached-audit-execution-20261029'
    private.mkdir(mode=0o700, exist_ok=False)
    variants = json.loads((ROOT / prepared['variants_file']).read_text())
    records, collections = [], []
    for case in cases:
        record = next(x for x in prepared['cases'] if x['id'] == case.input.task_id)
        row = json.loads((ROOT / record['source_record'] / 'row.json').read_text())
        reference = next(v for v in variants if v['case'] == case.input.task_id and v['variant'] == 'reference')
        counter = next(v for v in variants if v['case'] == case.input.task_id and v['variant'] == 'counterexample')
        payload = json.loads((ROOT / reference['payload']).read_text())
        payload['collect_only'] = True
        path = private / (case.input.task_id + '-collection.json')
        save(path, payload)
        collections.append({'case_id': case.input.task_id, 'payload': str(path.relative_to(ROOT)),
            'sha256': sha(path), 'archive_sha256': payload['archive_sha256']})
        records.append({'case_id': case.input.task_id, 'reference': reference['artifact'],
            'counterexample': counter['artifact'], 'upstream_bug_aliases': row['FAIL_TO_PASS'],
            'audit': True, 'snapshot_guard': 'tests/test_aeep_preservation.py::test_snapshot_preserved'})
    record_path = private / 'records.json'
    save(record_path, records)
    reused = {'directory': str(OLD.relative_to(ROOT)), 'image_id': old_parent['image'],
        'files': {str((OLD / name).relative_to(ROOT)): sha(OLD / name)
            for name in ('operation-review.json', 'execution-result.json', 'completion-audit.json')},
        'no_new_runtime_probes': True, 'new_subjects_still_require_reproduction': True}
    reused['files'][previous['parent_review']] = sha(ROOT / previous['parent_review'])
    for file in OLD.glob('raw-observation-*.json'):
        reused['files'][str(file.relative_to(ROOT))] = sha(file)
    paths = [*HERE.glob('*.py'), *sorted((HERE / 'runtime-execution').glob('*.py')),
        *(HERE / name for name in ('source-review.json', 'source-review-original.json',
            'jsonpickle-source-scope.json', 'prepared-cases.json', 'preparation-attempt1.json')),
        ROOT / prepared['cases_file'], ROOT / prepared['variants_file'], record_path,
        ROOT / 'docs/ASSESSMENT_TESTING.md', ROOT / 'docs/aeep-toolkit/CONTINUATION.md',
        ROOT / 'docs/aeep-toolkit/DECISIONS.md',
        HERE.parent / 'repository-cached-git-20261029/provisional-pool.json']
    for description in prepared['cases']:
        for item in description['license_records']:
            paths.append(ROOT / item['path'])
    for case in cases:
        paths += [Path(asset.path) for asset in (case.truth.source, case.truth.tests, case.reference, *case.truth.wheels)]
    for entry in [*variants, *collections]:
        paths.append(ROOT / entry['payload'])
    for record in json.loads((HERE / 'source-review.json').read_text())['sources']:
        paths += [ROOT / record['private_cache'] / 'row.json', ROOT / record['private_cache'] / 'source.tar.gz']
    paths += [ROOT / name for name in reused['files']]
    assets = {str(path.resolve()): sha(path) for path in paths}
    assert all(Path(name).is_file() and not Path(name).is_symlink() for name in assets)
    for path in [*HERE.glob('*.py'), *sorted((HERE / 'runtime-execution').glob('*.py'))]:
        ast.parse(path.read_text())
    subject = AssessmentSubject(kind='command', location=str(private), dependency_digests=assets,
        description='Two source-grounded authored fixed-snapshot library audits. No models,builds,downloads or project installation.')
    env = next(k for k, v in documents.items() if v['kind'] == 'environment')
    request = RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
        subject_digest=content_digest(subject), recipe_digest=content_digest(recipe), mapping_digest=content_digest(recipe),
        environment_digest=env, authorization_id='onboarding', seed=129,
        definition_digests=list(documents), runtime_dependencies=runtime_dependencies())
    new = {content_digest(value): {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
        for kind, identity, value in [('subject', subject.subject_id, subject),
                                     ('recipe_materialization_request', request.plan_id, request)]}
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=previous['authorization_digest'],
        subject_digests=[content_digest(subject)], recipe_digests=[content_digest(recipe)],
        environment_digests=[env], reviewed_digests=[*documents, *new])
    parent = {**old_parent, 'recipe': recipe.model_dump(mode='json'), 'documents': documents,
        'request': request.model_dump(mode='json'), 'host_canary': canary, 'source_digest': source}
    parent_path = HERE / 'observer-envelope.json'
    save(parent_path, parent)
    assets[str(parent_path.resolve())] = sha(parent_path)
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as db:
        counters = list(db.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert counters == [13327, 3755, 120125.71116234409, '0.0']
    review = {'purpose': 'Reproduce two authored source audit graders;backend conformance reused only at identical source/image/executor/environment bindings.',
        'source_digest': source, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'authorization_digest': previous['authorization_digest'], 'assets': assets,
        'parent_review': str(parent_path.relative_to(ROOT)), 'parent_review_sha256': sha(parent_path),
        'cases_file': prepared['cases_file'], 'records_file': str(record_path.relative_to(ROOT)),
        'request': request.model_dump(mode='json'), 'new_documents': new,
        'reviewed_document_digests': [*documents, *new], 'amendment': amendment.model_dump(mode='json'),
        'active_case_ids': [c.input.task_id for c in cases], 'collections': collections,
        'required_count_bounds': {c.input.task_id: [len(c.truth.pass_to_pass), 256] for c in cases},
        'derived_directory': str((private / 'derived').relative_to(ROOT)),
        'method_sha256': sha(HERE / 'runtime-execution/native_scope.py'),
        'driver_files': {name: sha(HERE / 'runtime-execution' / name) for name in ('run.py', 'audit-execution.py', 'classify.py', 'operator_output.py', 'native_scope.py', 'review-budget.py', 'reuse_conformance.py')},
        'reused_conformance': reused, 'parent_image': old_parent['image'], 'host_canary': canary,
        'maximum_contained_calls': 6, 'maximum_operations': 8, 'maximum_reserved_seconds': 360,
        'maximum_model_turns': 0, 'cash_usd': 0, 'maximum_builds': 0, 'maximum_downloads': 0,
        'automatic_retry': False, 'grant_before_preparation': counters,
        'permissions': ['At most two native collections and four reference/counterexample calls,on the exact retained image and shared-v6 programs. No probe or old study replay.',
            'Exhaustive disjoint native alias groups freeze before body observations;all published assertions plus explicit byte-preservation guard remain. Required scope30/83minimum,256maximum per case;no outcome-based dropping/remapping.',
            'No project installer/version metadata fabrication. Upstream version fallbacks remain. Four unchanged core wheels load privately;no new dependency.',
            'Retain receipts and at most8192bytes per failed public log. Remove only new owned containers and unchanged canary;keep all images and caches.'],
        'no_authority_for': ['Models,cash,downloads,installs,builds,pulls,new destinations/services,credentials,activation,publication/release or image/volume/backup deletion.',
            'No assertion/source/reference/fault/scope changes after outcomes,no uncertain replay,no automatic retries,no allowance refund/reset.'],
        'failure_policy': 'One initial attempt. Known completed and cleaned-up case collection/reference failures remain excluded;independent cases continue. Common authority,identity,accounting or cleanup uncertainty stops dispatch. No automatic retry.',
        'approval_reason': 'The continuation reserves untrusted software execution and CONTINUATION.md requires applicable container authority. Completed d1caf28b covered Dead and frozen JSON-logger controls,not these sources. Finite definition preparation is delegated;no architecture or budget decision.',
        'prepared_only': True, 'actual_external_source_execution': False,
        'qualification_comparative_usefulness_selection_resource_human_release': False}
    save(HERE / 'operation-review.json', review)
    print(json.dumps({'prepared': True, 'review_sha256': sha(HERE / 'operation-review.json'),
        'assets': len(assets), 'calls': 6, 'operations': 8, 'reserved_seconds': 360}))


if __name__ == '__main__':
    main()
