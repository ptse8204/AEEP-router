"""Prepare cached suites with explicit pytest plugins; execute no subject code."""
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
    # Original addopts still apply; every needed plugin is operator-declared.
    paths = set(kwargs['test_paths'])
    plugins = ['pytest_asyncio.plugin']
    if paths & {'tests/server/fastmcp/test_func_metadata.py', 'tests/server/fastmcp/test_server.py'}:
        plugins.append('anyio.pytest_plugin')
    if 'tests/test_goodconf.py' in paths or 'tests/main/test_main.py' in paths or 'tests/unit/container/test_decorator.py' in paths:
        plugins.append('pytest_cov.plugin')
    if 'tests/test_parser.py' in paths:
        plugins.append('pytest_benchmark.plugin')
    return SuiteTruthV3(**{**kwargs, 'pytest_plugins': plugins}, patch_encoding='gzip-json')


async def main():
    closure = json.loads((HERE / 'runtime-support-review.json').read_text())
    assert closure['complete_static_dependency_closure']
    specification = importlib.util.spec_from_file_location('existing_inert_case_curator', HERE.parent / 'repository-corpus-expansion-20261022/prepare-cases.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module.HERE = HERE
    module.OUT = ROOT / '.aeep/repository-supported-suite-cases-20261027-v2'
    module.ENTRIES = [
        ('modelcontextprotocol__python-sdk-222', False, []),
        ('modelcontextprotocol__python-sdk-384', True, []),
        ('lincolnloop__goodconf-51', True, []),
        ('elementsinteractive__twyn-317', False, []),
        ('reagento__dishka-512', False, []),
        ('prometheus__client_python-1134', True, []),
    ]
    module.RepositorySuiteCase = case_model
    module.SuiteTruth = module.SuiteTruthV2 = truth
    module.patch_artifact = compressed_patch_artifact
    await module.main()
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    cases = json.loads((ROOT / prepared['cases_file']).read_text())
    for case, description in zip(cases, prepared['cases'], strict=True):
        description['explicit_plugins'] = case['truth']['pytest_plugins']
    prepared.update(runtime_support_manifest=str((HERE / 'runtime-support-review.json').relative_to(ROOT)), runtime_supports_installed=False, external_subject_execution=False, first_party_preparer_reused='repository-corpus-expansion-20261022/prepare-cases.py', selection='Cached source-body and dependency review, not model outcomes. Three explicitly authored audits; remaining tasks retain upstream repair references. No stage assignments frozen.')
    (HERE / 'prepared-cases.json').write_text(json.dumps(prepared, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
