"""Reuse inert case preparation for the proposed shared grader runtime."""
import asyncio
import importlib.util
import json
from pathlib import Path

from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteTruthV3, compressed_patch_artifact

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def case_model(**kwargs):
    return RepositorySuiteCase(**{**kwargs, 'schema_version':'assessment.repository-suite-case.v3'})


def truth(**kwargs):
    paths = set(kwargs['test_paths'])
    plugins = ['pytest_django.plugin'] if 'tests/templatetags/test_bird.py' in paths else ['pytest_asyncio.plugin'] if 'tests/test_integration.py' in paths else []
    return SuiteTruthV3(**{**kwargs, 'pytest_plugins':plugins}, patch_encoding='gzip-json')


async def main():
    closure = json.loads((HERE / 'runtime-install-review.json').read_text())
    assert closure['complete_static_dependency_closure'] and len(closure['pins']) == 14
    scopes = json.loads((HERE / 'git-tree-source-scopes.json').read_text())
    scopes['sources'] += json.loads((HERE / 'prometheus-git-tree-source-scope.json').read_text())['sources']
    scopes['sources'] += [x for x in json.loads((HERE.parent / 'repository-compact-patches-20261022/git-tree-source-scopes.json').read_text())['sources'] if x['instance_id']=='tobymao__sqlglot-7479']
    (HERE/'combined-git-tree-scopes.json').write_text(json.dumps(scopes,indent=2)+'\n')
    # Give the unchanged preparer a complete source index; it resolves explicit scopes first.
    index=json.loads((HERE/'source-review.json').read_text())
    indexed={x['instance_id'] for x in index['sources']}
    index['sources'] += [x for x in scopes['sources'] if x['instance_id'] not in indexed]
    (HERE/'combined-source-review.json').write_text(json.dumps(index,indent=2)+'\n')
    for name in ('pure-wheel-review.json',):
        (HERE/name).write_bytes((HERE.parent/'repository-corpus-expansion-20261022'/name).read_bytes())
    spec=importlib.util.spec_from_file_location('unchanged_inert_curator',HERE.parent/'repository-corpus-expansion-20261022/prepare-cases.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.HERE=HERE;module.OUT=ROOT/'.aeep/repository-workload-batch-20261022-cases-v3'
    sql=[x['instance_id'] for x in scopes['sources'] if x['status']=='STATIC_SCOPE_REVIEW_REQUIRED' and x['repository']=='tobymao/sqlglot']
    module.ENTRIES=[('python-scim__scim2-models-90',False,[]),('python-scim__scim2-models-120',False,[]),('python-scim__scim2-models-126',False,[]),
                    ('joshuadavidthomas__django-bird-239',False,[]),('reagento__dishka-512',False,[]),('hynek__svcs-140',True,[]),('prometheus__client_python-1134',True,[]),
                    *[(identity,False,[]) for identity in sql]]
    module.RepositorySuiteCase=case_model;module.SuiteTruth=module.SuiteTruthV2=truth;module.patch_artifact=compressed_patch_artifact
    # The preparer's exact metadata paths are changed here, before any execution review.
    from unittest.mock import patch
    original=Path.read_text
    def metadata(path,*args,**kwargs):
        replacement={HERE/'source-review.json':HERE/'combined-source-review.json',HERE/'git-tree-source-scopes.json':HERE/'combined-git-tree-scopes.json', HERE/'source-scope-review.json':HERE/'source-scope-review-v3.json'}.get(path,path)
        return original(replacement,*args,**kwargs)
    with patch.object(Path,'read_text',metadata):
        await module.main()
    prepared=json.loads((HERE/'prepared-cases.json').read_text())
    prepared['runtime_support_manifest']='reports/toolkit-v2/c13/repository-workload-batch-20261022/runtime-install-review.json'
    prepared['runtime_supports_installed']=False
    prepared['external_subject_execution']=False
    prepared['first_party_preparer_reused']='reports/toolkit-v2/c13/repository-corpus-expansion-20261022/prepare-cases.py'
    prepared['new_runtime_notes']='14 exact wheels proposed for one private offline image. Plugins explicitly declared per case. No project installer, changed upstream assertions, OS package or host setup.'
    (HERE/'prepared-cases.json').write_text(json.dumps(prepared,indent=2)+'\n')


if __name__=='__main__':
    asyncio.run(main())
