"""Rebuild the frozen historical definition, not a later mutable case cache."""
import hashlib
import json
from pathlib import Path
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
path=HERE.parent/'repository-supported-suites-20261027/observer-envelope.json';frozen=json.loads(path.read_text())['recipe']
cases=[RepositorySuiteCase.model_validate(c) for c in frozen['generator_config']['cases']]
rebuilt=repository_suite_recipe(cases)
expected='d02cb9538fe9a42470612f799912b7907c3b72ffd6a8ab0c42661b22e3ab4b0f'
assert content_digest(frozen)==content_digest(rebuilt)==expected
cache=ROOT/'.aeep/repository-compact-patches-20261022-envelope/cases.json';later=[RepositorySuiteCase.model_validate(c) for c in json.loads(cache.read_text())]
assert len(later)==len(cases)
for original,current in zip(cases,later,strict=True):
    left=original.model_dump(mode='json');right=current.model_dump(mode='json')
    left.pop('fault_outputs');right.pop('fault_outputs');assert left==right
value={'passed':True,'retained_recipe_digest':expected,'rebuilt_recipe_digest':content_digest(rebuilt),'actual_frozen_recipe_serialization_unchanged':True,'frozen_document':str(path.relative_to(ROOT)),'frozen_document_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'initial_mismatch':'The selected mutable cache has different Marshmallow fault bytes; only that fault and its derived recipe ID differed. It is not the frozen d02 definition. No cache was overwritten and no source correction was needed.','later_cache_recipe_digest':content_digest(repository_suite_recipe(later)),'historical_qualification_transferred':False,'source_digest':verification_source_digest(ROOT)}
(HERE/'legacy-compatibility.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
