"""Prepare exact changed-wheel and cached docs drivers; no installation/checker run."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];BASE=ROOT/'reports/toolkit-v2/integration-completion'
OLD=BASE/'package-review-test-roots-20261027';PKG=BASE/'package-review-large-archives-20261027';DOC=BASE/'lychee-large-archives-review-20261027'
PKG.mkdir(exist_ok=False);DOC.mkdir(exist_ok=False)
s=(OLD/'prepare-review.py').read_text().replace("OLD=HERE.parent/'package-review-task-delivery-20261023'","OLD=HERE.parent/'package-review-test-roots-20261027'").replace('repository-test-roots-20261027','repository-large-archives-20261027').replace('.aeep/repository-test-roots-envelope-20261027/cases.json','.aeep/repository-large-execution-cases-20261027/development-cases.json')
s=s.replace("'aeep/assessment/repository_suites.py',","'aeep/assessment/repository_suites.py','aeep/assessment/adapters.py','aeep/assessment/containment.py',")
s=s.replace("'installed_module_sha256':sha(ROOT/'src/aeep/assessment/repository_suites.py'),","'installed_module_sha256':sha(ROOT/'src/aeep/assessment/repository_suites.py'),\n        'installed_module_hashes':{n:sha(ROOT/'src'/Path(n.replace('.','/')+'.py')) for n in ('aeep.assessment.repository_suites','aeep.assessment.adapters','aeep.assessment.containment')},\n        'installed_schema_sha256':sha(ROOT/'schemas/assessment-repository-suite-case.schema.json'),")
s=s.replace('compact-output v4 test-root recipe export','v5 larger-source recipe export')
s=s.replace('Preserves published package-local test paths through explicit v4 operator-owned test roots.','Adds an explicit v5 larger-source profile and bounded operator stdin transport. Legacy profiles retain their limits and frozen recipe identity.')
s=s.replace('Case v4 declares exact protected test roots; v1-v3 keep their serialized meanings and stock observer bytes are unchanged.','V5 requires an explicit larger archive profile; v1-v4 retain their limits and stock observer bytes are unchanged.')
(PKG/'prepare-review.py').write_text(s)
s=(OLD/'run_review.py').read_text().replace("case['schema_version']=='assessment.repository-suite-case.v4'","case['schema_version']=='assessment.repository-suite-case.v5'").replace("c['truth']['pytest_plugins']==[] and c['truth']['test_roots']==['tests']","c['truth']['pytest_plugins']==['pytest_mock','_hypothesis_pytestplugin'] and c['truth']['test_roots']==['tests'] and c['truth']['archive_profile']=='repository-v1'")
s=s.replace('truth=suites.SuiteTruthV4.model_validate','truth=suites.SuiteTruthV5.model_validate').replace("assert truth.test_roots==['tests']","assert truth.test_roots==['tests'] and truth.archive_profile=='repository-v1'")
s=s.replace("assert hashlib.sha256(Path(suites.__file__).read_bytes()).hexdigest()==review['installed_module_sha256']","""assert hashlib.sha256(Path(suites.__file__).read_bytes()).hexdigest()==review['installed_module_sha256']
import importlib
for name,sha in review['installed_module_hashes'].items():
    assert hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest()==sha
schema=Path(sysconfig.get_path('data'))/'share/aeep/schemas/assessment-repository-suite-case.schema.json'
assert hashlib.sha256(schema.read_bytes()).hexdigest()==review['installed_schema_sha256']
fixture=suites.pack_files({'library/fixture.py':b'# first-party fixture', 'public.bin':b'x'*4000001},large=True)
assert len(suites.archive_files(fixture,large=True)['public.bin'])==4000001
try:
    suites.archive_files(fixture)
except Exception:
    pass
else:
    raise AssertionError('Compact profile accepted the expanded fixture')""")
(PKG/'run_review.py').write_text(s)
OLD=BASE/'lychee-test-roots-review-20261027'
for name in ('sandbox-template.sb','sandbox-preflight.py','run-review.py'):shutil.copyfile(OLD/name,DOC/name)
s=(OLD/'prepare-review.py').read_text().replace("OLD=HERE.parent/'lychee-task-delivery-review-20261023'","OLD=HERE.parent/'lychee-test-roots-review-20261027'").replace('repository-test-roots-20261027','repository-large-archives-20261027').replace('protected-test-roots runtime/package/docs','larger-repository runtime/package/docs')
(DOC/'prepare-review.py').write_text(s)
# The same first-party six-boundary preflight gets its own new scratch/result.
s=(HERE.parent/'repository-test-roots-20261027/check-docs-sandbox.py').read_text().replace('lychee-test-roots-review-20261027','lychee-large-archives-review-20261027')
(HERE/'check-docs-sandbox.py').write_text(s)
print('Prepared first-party package/docs drivers without installing or executing the checker.')
