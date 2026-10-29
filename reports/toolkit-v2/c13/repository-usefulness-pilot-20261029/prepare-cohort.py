"""Freeze a bounded development cohort as data; execute no repository software."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, archive_files, repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
POOL = HERE.parent / 'repository-cached-git-20261029/provisional-pool.json'
PUBLIC = ROOT / '.aeep/repository-usefulness-pilot-20261029/public'
SELECTED = [
    'matthewwithanm__python-markdownify-200',
    'python-markdown__markdown-1587',
    'spulec__freezegun-582',
    'jpadilla__pyjwt-1040-declared-tests',
    'sciunto-org__python-bibtexparser-515-declared-tests',
    'joke2k__django-environ-592-declared-tests',
    'serge-sans-paille__beniget-121-declared-tests-py313-truth',
    'AbsaOSS__generate-release-notes-207',
    'gerlero__foamlib-315',
    'oOo0oOo__leanclient-24-declared-tests',
    'python-scim__scim2-models-126-declared-tests',
    'researchobject__ro-crate-py-248-declared-tests',
    'canopen-python__canopen-613-declared-tests',
    'tefra__xsdata-1126-issue-behavior-audit',
    'MahjongRepository__mahjong-62-aeep-contract-audit',
    'iluvcapra__pycmx-12-aeep-contract-audit',
    'scitokens__scitokens-202-aeep-contract-audit',
    'gidgethub__gidgethub-225-aeep-contract-audit',
    'hynek__svcs-140-aeep-contract-audit',
    'lincolnloop__goodconf-51-aeep-contract-audit',
    'prometheus__client_python-1134-aeep-contract-audit',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    manifest = json.loads(POOL.read_text())
    pool_path = ROOT / manifest['cases_file']
    assert sha(pool_path) == manifest['cases_file_sha256']
    pool = [RepositorySuiteCase.model_validate(value) for value in json.loads(pool_path.read_text())]
    by_id = {case.input.task_id: case for case in pool}
    assert len(SELECTED) == len(set(SELECTED)) == 21
    chosen = [by_id[identity] for identity in SELECTED]
    repositories = {case.source_repository.casefold() for case in chosen}
    assert len(repositories) == 21
    assert Counter(case.input.family for case in chosen) == Counter({
        'single-file-repair': 7, 'multi-file-repair': 7, 'contract-audit': 7})
    # Two families alternate before audits; scheduling order remains paired/randomized by BenchmarkRunner.
    chosen = [chosen[index] for group in zip(range(7), range(7, 14), range(14, 21)) for index in group]
    PUBLIC.mkdir(parents=True, exist_ok=False)
    result = []
    records = []
    assets = {}
    for original in chosen:
        assert original.schema_version != 'aeep.repository-suite-case.v6'
        data = original.truth.source.read()
        assert len(data) <= 650_000
        files = archive_files(data)
        target = PUBLIC / (original.truth.source.sha256 + '.tar.gz')
        target.write_bytes(data)
        target.chmod(0o444)
        value = original.model_dump(mode='json')
        value['split'] = 'development'
        value['used_for_development'] = True
        value['truth']['source']['path'] = str(target)
        case = RepositorySuiteCase.model_validate(value)
        assert case.input == original.input and case.reference == original.reference
        assert case.fault_outputs == original.fault_outputs
        for asset in (original.truth.source, original.truth.tests, original.reference, *original.truth.wheels):
            asset.read()
            assets[asset.path] = asset.sha256
        assets[str(target)] = sha(target)
        result.append(case)
        records.append({
            'task_id': case.input.task_id, 'family': case.input.family,
            'repository': case.source_repository, 'revision': case.source_revision,
            'origin_kind': case.origin_kind, 'license': case.license,
            'provenance': case.provenance, 'case_schema': case.schema_version,
            'public_input_sha256': content_digest(case.input),
            'public_archive': case.truth.source.model_dump(mode='json'),
            'archive_files': len(files), 'expanded_bytes': sum(map(len, files.values())),
            'required_identities': len(case.truth.fail_to_pass) + len(case.truth.pass_to_pass),
            'historical_runtime_binding': manifest['source_runtime_bindings'][case.input.task_id],
            'current_model_grading_qualification': False,
        })
    recipe = repository_suite_recipe(result)
    assert all(case.split == 'development' and case.used_for_development for case in result)
    exposed = [case for case in pool if case.source_repository.casefold() in repositories]
    remaining = [case for case in pool if case.source_repository.casefold() not in repositories]
    out = {
        'purpose': '21-pair development usefulness comparison; no formal qualification/admission',
        'source_digest': verification_source_digest(ROOT), 'pool_manifest_sha256': sha(POOL),
        'pool_case_count': len(pool), 'selected_count': len(result), 'repository_count': len(repositories),
        'family_counts': dict(Counter(case.input.family for case in result)),
        'public_root': str(PUBLIC), 'public_archive_bytes': sum(path.stat().st_size for path in PUBLIC.iterdir()),
        'only_selected_hash_named_public_archives': True, 'models_or_workers_started': False,
        'cases': records, 'assets': assets,
        'formal_exclusions_after_model_exposure': [case.input.task_id for case in exposed],
        'formal_exclusion_count_after_model_exposure': len(exposed),
        'provisional_cases_remaining_after_exposure': len(remaining),
        'remaining_family_counts_after_exposure': dict(Counter(case.input.family for case in remaining)),
        'development_cases_cannot_be_reused_even_in_formal_training': True,
        'formal_141_case_campaign_unchanged': True,
        'adopted_cases': 0, 'qualification': False, 'comparative_value_observed': False,
    }
    save(HERE / 'cases.json', [case.model_dump(mode='json') for case in result])
    save(HERE / 'recipe.json', recipe.model_dump(mode='json'))
    save(HERE / 'cohort.json', out)
    print(json.dumps({key: value for key, value in out.items() if key not in ('cases', 'assets', 'formal_exclusions_after_model_exposure')}))


if __name__ == '__main__':
    main()
