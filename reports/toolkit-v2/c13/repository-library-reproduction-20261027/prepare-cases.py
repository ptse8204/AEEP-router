"""Prepare two corrected-snapshot audits as inert data, retaining upstream assertions."""
import asyncio
import importlib.util
from pathlib import Path

from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteTruthV3, compressed_patch_artifact

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def case_model(**kwargs):
    return RepositorySuiteCase(**{**kwargs, 'schema_version': 'assessment.repository-suite-case.v3'})


def truth(**kwargs):
    return SuiteTruthV3(**kwargs, pytest_plugins=[], patch_encoding='gzip-json')


async def main():
    spec = importlib.util.spec_from_file_location('existing_inert_case_curator', HERE.parent / 'repository-corpus-expansion-20261022/prepare-cases.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.HERE = HERE
    module.OUT = ROOT / '.aeep/repository-library-audits-20261027'
    module.ENTRIES = [('CrossGL__crosstl-257', True, []),
                      ('marshmallow-code__marshmallow-sqlalchemy-640', True, ['marshmallow'])]
    module.RepositorySuiteCase = case_model
    module.SuiteTruth = module.SuiteTruthV2 = truth
    module.patch_artifact = compressed_patch_artifact
    await module.main()


if __name__ == '__main__':
    asyncio.run(main())
