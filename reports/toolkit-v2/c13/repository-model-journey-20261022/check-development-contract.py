"""Validate inert plan/artifact/budget contracts; no host,worker or model launch."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.assessment.adapters import prepare_context
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,archive_files
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
    module=load('inert_repository_journey',HERE/'run-model-journey.py');proposal=json.loads((HERE/'collector-definitions.json').read_text())
    synthetic={'boundaries':{role:{'conformance_digest':character*64} for role,character in [('control','a'),('treatment','b')]},'differential_conformance_digest':'c'*64}
    pair,recipe,mapping,environment,plan,definitions=module.construct(proposal,synthetic)
    assert plan.schema_version=='assessment.plan.v1' and plan.comparison is None and plan.pilot is None
    assert len(plan.suite.cases)==3 and len(plan.suite.routes)==2 and plan.suite.repetitions==1
    assert all(c.split.value=='training' for c in plan.suite.cases) and len({c.template_family for c in plan.suite.cases})==3
    assert pair.treatment.config['invocation']['exposure']=='optional' and pair.control.config['invocation']['mode']=='turn'
    assert environment.kind=='container' and environment.container_image.endswith('324a1fee6ee58475ecfdc659c98be5b5a8480fae4389b26b13b5b0b43bc32d2b')
    checks=0
    for raw in recipe.generator_config['cases']:
        case=RepositorySuiteCase.model_validate(raw);assert case.used_for_development and case.split=='development'
        for spec in (pair.control,pair.treatment):
            context=ExecutionContext(request=ActionRequest(capability=recipe.capability,input=case.input.model_dump(mode='json')),spec=spec,estimate=spec.estimate,attempt=1)
            prepared,adapter=prepare_context(context);value=prepared.request.input
            assert value['base_sha256']==content_digest(case.input) and value['source_b64']
            import base64
            archive=base64.b64decode(value['source_b64'],validate=True);assert hashlib.sha256(archive).hexdigest()==case.input.source_sha256
            assert archive_files(archive) and adapter.input_transform=='repository_archive:1';checks+=1
    budget=load('tested_review_budget',HERE/'review-budget.py');guard_checks=budget.self_check()
    for path in HERE.glob('*.py'):ast.parse(path.read_text())
    result={'passed':True,'pure_synthetic_boundary_fixture_only':True,'actual_worker_conformance':False,'new_models_or_workers':0,'development_cases':3,'future_holdout_eligible':False,'planned_task_turns':6,'artifact_bindings_checked':checks,'review_budget_checks':guard_checks,'optional_candidate':True,'formal_study_counts_changed':False,'qualification_or_efficacy_claim':False}
    (HERE/'development-contract-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
