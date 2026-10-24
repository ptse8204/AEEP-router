"""Reuse the protected suite adapter to prepare five inert task contracts."""
import asyncio
import importlib.util
import json
from pathlib import Path

from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteTruthV3, compressed_patch_artifact

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def case_model(**kwargs):
    return RepositorySuiteCase(**{**kwargs, 'schema_version': 'assessment.repository-suite-case.v3'})


def truth(**kwargs):
    paths = set(kwargs['test_paths'])
    plugins = ['pytest_django.plugin'] if 'tests/test_baker.py' in paths else ['pytest_asyncio.plugin', 'pytest_subtests.plugin'] if 'tests/test_kv_config.py' in paths else []
    return SuiteTruthV3(**{**kwargs, 'pytest_plugins': plugins}, patch_encoding='gzip-json')


async def main():
    closure = json.loads((HERE / 'runtime-support-review.json').read_text())
    assert closure['complete_static_dependency_closure'] and len(closure['pins']) == 16
    (HERE / 'source-scope-review.json').write_text('{"sources": []}\n')
    (HERE / 'git-tree-source-scopes.json').write_text('{"sources": []}\n')
    (HERE / 'pure-wheel-review.json').write_bytes((HERE.parent / 'repository-corpus-expansion-20261022/pure-wheel-review.json').read_bytes())
    spec = importlib.util.spec_from_file_location('existing_inert_case_curator', HERE.parent / 'repository-corpus-expansion-20261022/prepare-cases.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.OUT = ROOT / '.aeep/repository-independent-cases-20261024-v2'
    module.ENTRIES = [
        ('AzureAD__microsoft-authentication-library-for-python-795', True, []),
        ('agronholm__sqlacodegen-370', False, []),
        ('lmstudio-ai__lmstudio-python-110', False, []),
        ('model-bakers__model_bakery-520', False, []),
        ('ucfopen__canvasapi-716', False, []),
    ]
    module.RepositorySuiteCase = case_model
    module.SuiteTruth = module.SuiteTruthV2 = truth
    module.patch_artifact = compressed_patch_artifact
    await module.main()
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    actual_cases = json.loads((ROOT / prepared['cases_file']).read_text())
    for case, description in zip(actual_cases, prepared['cases'], strict=True):
        description['explicit_plugins'] = case['truth']['pytest_plugins']
    prepared.update(runtime_support_manifest=str((HERE / 'runtime-support-review.json').relative_to(ROOT)), runtime_supports_installed=False, external_subject_execution=False, intended_runtime='Existing image324a1fee plus exactly16 reviewed wheel supports; not built or executed.', selection='Five distinct repositories; four published single-file repairs and one explicitly authored MSAL corrected-snapshot audit. No development model outcomes used or stage assignment frozen.')
    (HERE / 'prepared-cases.json').write_text(json.dumps(prepared, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
