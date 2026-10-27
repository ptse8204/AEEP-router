"""Prepare current-wheel and cached-checker drivers; no install/checker execution."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=ROOT/'reports/toolkit-v2/integration-completion'
PKG=BASE/'package-review-test-roots-20261027'
DOC=BASE/'lychee-test-roots-review-20261027'
PKG.mkdir(exist_ok=False);DOC.mkdir(exist_ok=False)
old=BASE/'package-review-task-delivery-20261023'
s=(old/'run_review.py').read_text().replace("case['schema_version']=='assessment.repository-suite-case.v3'","case['schema_version']=='assessment.repository-suite-case.v4'")
s=s.replace("c['truth']['pytest_plugins']==[] for c in explicit","c['truth']['pytest_plugins']==[] and c['truth']['test_roots']==['tests'] for c in explicit")
s=s.replace('truth=suites.SuiteTruthV3.model_validate','truth=suites.SuiteTruthV4.model_validate').replace("from aeep.assessment.repository_tasks import RepositoryPatch\npatch=", "assert truth.test_roots==['tests']\nfrom aeep.assessment.repository_tasks import RepositoryPatch\npatch=")
(PKG/'run_review.py').write_text(s)
s=(old/'prepare-review.py').read_text().replace("OLD=HERE.parent/'package-review-compact-patches-20261022'","OLD=HERE.parent/'package-review-task-delivery-20261023'")
s=s.replace("CAPTURE=ROOT/'reports/toolkit-v2/c13/repository-task-delivery-20261023'","CAPTURE=ROOT/'reports/toolkit-v2/c13/repository-test-roots-20261027'").replace('validation-final/','validation/')
s=s.replace("suite_cases='.aeep/repository-compact-patches-20261022-envelope/cases.json'","suite_cases='.aeep/repository-test-roots-envelope-20261027/cases.json'")
s=s.replace('compact-output v3 recipe export','compact-output v4 test-root recipe export')
s=s.replace('Protocol/case schemas and observer bytes are unchanged.','Case v4 declares exact protected test roots; v1-v3 keep their serialized meanings and stock observer bytes are unchanged.')
s=s.replace('Preserves safe worker cleanup/artifact metadata and bounded failure codes,and stops assessment after the first indeterminate invocation.','Preserves published package-local test paths through explicit v4 operator-owned test roots.')
(PKG/'prepare-review.py').write_text(s)
old=BASE/'lychee-task-delivery-review-20261023'
for name in ('sandbox-template.sb','sandbox-preflight.py'):shutil.copyfile(old/name,DOC/name)
s=(old/'run-review.py').read_text()
s=s.replace("    archive = Path(review['archive_path'])","    assert verification_source_digest(ROOT)==review['source_digest']\n    for name,expected in review['document_sha256'].items():assert sha(ROOT/name)==expected\n    archive = Path(review['archive_path'])")
s=s.replace('from pathlib import Path','from pathlib import Path\nfrom aeep.assessment.verification import verification_source_digest')
(DOC/'run-review.py').write_text(s)
s=(old/'prepare-review.py').read_text().replace("OLD=HERE.parent/'lychee-compact-patches-review-20261022'","OLD=HERE.parent/'lychee-task-delivery-review-20261023'").replace('task-delivery runtime/package/docs','protected-test-roots runtime/package/docs').replace('repository-task-delivery-20261023/validation-final','repository-test-roots-20261027/validation')
s=s.replace("    (HERE/'operation-review.json').write_text", "    review['document_sha256']={name:sha(ROOT/name) for name in review['documents']}\n    (HERE/'operation-review.json').write_text")
(DOC/'prepare-review.py').write_text(s)
print('Prepared package/docs drivers only.')
