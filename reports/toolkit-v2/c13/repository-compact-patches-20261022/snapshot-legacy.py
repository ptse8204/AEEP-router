"""Record legacy v1/v2 definitions without running any repository subject."""
import hashlib,json,sys
from pathlib import Path
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,SuiteTruth,SuiteTruthV2,repository_suite_recipe
r=Path.cwd();p=Path(__file__).resolve().parent
paths=['.aeep/repository-suite-integration-20261022-v2/protected/cases.json','.aeep/repository-replacement-runtime-20261022-v5/observer-development-cases.json']
result={}
for path in paths:
 cases=[RepositorySuiteCase.model_validate(x) for x in json.loads((r/path).read_text())]
 recipe=repository_suite_recipe(cases)
 result[path]={'cases':[content_digest(c) for c in cases],'recipe_id':recipe.recipe_id,'recipe_digest':content_digest(recipe),'truth_schema':content_digest(SuiteTruth.model_json_schema()),'plugin_truth_schema':content_digest(SuiteTruthV2.model_json_schema())}
(p/('legacy-'+sys.argv[1]+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
