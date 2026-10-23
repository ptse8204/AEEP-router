"""Reuse the reviewed inert source preparer with the explicit v3 encoding."""
import asyncio
import importlib.util
import json
from pathlib import Path

from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteTruthV3, compressed_patch_artifact

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'repository-corpus-expansion-20261022'


def case_model(**kwargs):
    return RepositorySuiteCase(**{**kwargs, 'schema_version': 'assessment.repository-suite-case.v3'})


def plain_truth(**kwargs):
    return SuiteTruthV3(**kwargs, patch_encoding='gzip-json')


def plugin_truth(**kwargs):
    # The unchanged source's mocker fixtures require the already installed plugin.
    return SuiteTruthV3(**{**kwargs, 'pytest_plugins': ['pytest_mock', *kwargs['pytest_plugins']]}, patch_encoding='gzip-json')


async def main():
    for name in ('source-review.json', 'source-scope-review.json', 'git-tree-source-scopes.json', 'pure-wheel-review.json'):
        (HERE / name).write_bytes((PRIOR / name).read_bytes())
    scope_file = HERE / 'git-tree-source-scopes.json'
    scopes = json.loads(scope_file.read_text())
    more = json.loads((HERE.parent / 'repository-corpus-expansion-batch2-20261022/git-tree-source-scopes.json').read_text())
    scopes['sources'].extend(more['sources'])
    assert len(scopes['sources']) == 4
    scope_file.write_text(json.dumps(scopes, indent=2) + '\n')
    spec = importlib.util.spec_from_file_location('aeep_reviewed_inert_curator', PRIOR / 'prepare-cases.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.OUT = ROOT / '.aeep/repository-compact-patches-20261022-cases-v2'
    module.ENTRIES = [('tobymao__sqlglot-4643', False, []), ('tobymao__sqlglot-5256', False, []),
                      ('fabfuel__circuitbreaker-67', False, ['pytest-asyncio']),
                      ('tobymao__sqlglot-6374', False, []), ('tobymao__sqlglot-7479', False, [])]
    module.patch_artifact = compressed_patch_artifact
    module.SuiteTruth, module.SuiteTruthV2 = plain_truth, plugin_truth
    module.RepositorySuiteCase = case_model
    await module.main()
    path = HERE / 'prepared-cases.json'
    metadata = json.loads(path.read_text())
    assert metadata['prepared_cases'] == 5 and not metadata['errors']
    cases = [RepositorySuiteCase.model_validate(x) for x in json.loads((ROOT / metadata['cases_file']).read_text())]
    for description, case in zip(metadata['cases'], cases, strict=True):
        description['patch_encoding'] = 'gzip-json'
        description['explicit_plugins'] = case.truth.pytest_plugins
    metadata['preparation_reuse'] = {'first_party_preparer': str((PRIOR / 'prepare-cases.py').relative_to(ROOT)),
        'changes': ['new explicit gzip-json v3 metadata and artifacts', 'existing pytest_mock declared alongside existing asyncio plugin for Circuitbreaker'],
        'subject_code_executed': False, 'old_results_or_assets_modified': False}
    path.write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
