"""Reuse source-grounded inert audit preparation with the shared v6 contract."""
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil

from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteTruthV6, compressed_patch_artifact

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def case_model(**kwargs):
    return RepositorySuiteCase(**{**kwargs, 'schema_version': 'assessment.repository-suite-case.v6'})


def truth_model(**kwargs):
    for name in ('source', 'tests'):
        kwargs[name] = kwargs[name].model_dump(mode='json')
    kwargs['wheels'] = [item.model_dump(mode='json') for item in kwargs['wheels']]
    return SuiteTruthV6(**{**kwargs, 'pytest_plugins': [], 'patch_encoding': 'gzip-json',
        'test_roots': ['tests'], 'archive_profile': 'repository-v1', 'identity_format': 'pytest-native-v1'})


async def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 20 * 1024**2
    script = HERE.parent / 'repository-corpus-expansion-20261022/prepare-cases.py'
    spec = importlib.util.spec_from_file_location('unchanged_inert_audit_preparer', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.OUT = ROOT / '.aeep/repository-cached-audits-20261029-v2'
    module.ENTRIES = [('holoviz__param-1073', True, []), ('jsonpickle__jsonpickle-587', True, [])]
    module.RepositorySuiteCase = case_model
    module.SuiteTruth = module.SuiteTruthV2 = truth_model
    module.patch_artifact = compressed_patch_artifact
    await module.main()
    report = json.loads((HERE / 'prepared-cases.json').read_text())
    assert report['external_code_executed'] is False and report['models'] == 0
    assert report['prepared_cases'] == 2 and not report['errors']
    values = json.loads((ROOT / report['cases_file']).read_text())
    prior = json.loads((HERE.parent / 'repository-cached-git-20261029/provisional-pool.json').read_text())
    pool = json.loads((ROOT / prior['cases_file']).read_text())
    used = {(c['source_repository'].casefold(), c['source_revision']) for c in pool}
    for value, description in zip(values, report['cases'], strict=True):
        case = RepositorySuiteCase.model_validate(value)
        assert case.schema_version == 'assessment.repository-suite-case.v6'
        assert (case.source_repository.casefold(), case.source_revision) not in used
        assert case.input.family == 'contract-audit' and not case.truth.fail_to_pass
        assert len(case.truth.pass_to_pass) == len(description['upstream_required_identities']) + 1
        assert case.origin_kind == 'authored_control' and len(case.truth.wheels) == 4
    report.update(schema='assessment.repository-suite-case.v6',
        shared_observer_source='b09911a0b7b79f6f78a5371bbad53580ff0692fc3d371592a983437898a19fcf',
        source_grader_image='sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04',
        source_modules_installed=False, new_project_installer=False,
        notes='Authored fixed-snapshot audits with all original required assertions and one explicit byte-preservation guard. Published fixes are public inputs;empty reference and original-source negative remain private. Native collection/exhaustive mapping must freeze before body observations. No project metadata/version is fabricated;upstream fallbacks remain unchanged.',
        source_runtime_qualified=False, actual_source_execution_approved=False)
    (HERE / 'prepared-cases.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
