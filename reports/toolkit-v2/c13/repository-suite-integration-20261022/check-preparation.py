"""Read-only audit of prepared conformance scope; never launch its executors."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from aeep.assessment.models import (AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject,
    RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest)
from aeep.assessment.repository_suites import RepositorySuiteCase, archive_files
from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).parent
review_path = HERE / 'grader-operation-review.json'
review = json.loads(review_path.read_text())
checks = {}
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
checks['runner_bound'] = sha(HERE / 'run-grader-review.py') == review['runner_sha256']
checks['source_bound'] = verification_source_digest(ROOT) == review['source_digest']
checks['assets_unchanged'] = all(not Path(path).is_symlink() and sha(path)==value for path,value in review['assets'].items())
models = {'subject':AssessmentSubject,'environment':AssessmentEnvironment,'recipe':RecipeDefinition,
    'recipe_materialization_request':RecipeMaterializationRequest,'recipe_runtime':RecipeRuntimeBinding}
checks['documents_content_bound'] = all(content_digest(models[value['kind']].model_validate(value['document']))==key for key,value in review['documents'].items())
request = RecipeMaterializationRequest.model_validate(review['request'])
recipe = RecipeDefinition.model_validate(review['recipe'])
amendment = AssessmentScopeAmendment.model_validate(review['amendment'])
checks['request_scope_bound'] = (request.recipe_digest == content_digest(recipe)
    and request.recipe_digest in amendment.recipe_digests and request.subject_digest in amendment.subject_digests
    and request.environment_digest in amendment.environment_digests)
checks['same_v5_observer'] = recipe.extension.schema_version=='assessment.recipe-extension.v5' and recipe.extension.grader.config['timeout_seconds']==30
checks['finite_reservation'] = (review['maximum_contained_calls']==12 and review['maximum_operations']==14
    and review['maximum_reserved_seconds']==12*35+30+180 and review['maximum_model_turns']==review['cash_usd']==0
    and not review['network'] and not review['automatic_retry'])
cases = [RepositorySuiteCase.model_validate(value) for value in json.loads((ROOT/review['cases_file']).read_text())]
checks['three_real_development_origins'] = len(cases)==3 and all(case.origin_kind=='upstream_issue' and case.split=='development' and case.used_for_development for case in cases)
checks['nine_staged_payloads'] = len(review['variants'])==9 and all(sha(ROOT/item['payload'])==item['sha256'] and item['bytes']<=1_800_000 for item in review['variants'])
checks['three_synthetic_boundary_probes'] = len(review['probes'])==3 and all(sha(ROOT/item['payload'])==item['payload_sha256'] for item in review['probes'])
for item in review['probes']:
    import base64
    payload = json.loads((ROOT/item['payload']).read_text())
    files = archive_files(base64.b64decode(payload['archive']))
    assert set(files)=={'tests/test_boundary.py'}
    ast.parse(files['tests/test_boundary.py'])
checks['probe_source_parsed_only'] = True
checks['canary_not_created'] = not (ROOT/review['host_canary']).exists()
checks['execution_not_started'] = not (HERE/'grader-execution-started.json').exists()
image = subprocess.check_output([review['docker'],'--host',review['socket'],'image','inspect',review['image'],'--format','{{.Id}}'],timeout=20).decode().strip()
checks['existing_image_id_matches'] = image == review['image']
with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro',uri=True) as connection:
    grant = list(connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
checks['canonical_grant_preserved_and_fits_total_ceiling'] = grant[0]+14<=50000 and grant[1]<=6000 and grant[2]+630<=604800 and float(grant[3])==0
checks['storage_reserve'] = shutil.disk_usage(ROOT).free > 50*1024**3
result = {'passed':all(checks.values()),'checks':checks,'source_digest':review['source_digest'],
    'review_sha256':sha(review_path),'canonical_grant_snapshot':grant,'image':image,
    'external_code_executed':False,'models':0,'containers_started':0,'operations_reserved':0}
with (HERE/'grader-preparation-checks.json').open('x') as output:
    json.dump(result,output,indent=2);output.write('\n')
assert result['passed']
print(json.dumps(result))
