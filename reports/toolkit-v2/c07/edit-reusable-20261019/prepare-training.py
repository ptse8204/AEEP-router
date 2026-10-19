"""Freeze an inert diagnostic on the builder's original training inputs only."""
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.comparison import define
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentEnvironment, AssessmentPlan,
    AssessmentScopeAmendment, RecipeDefinition, ReviewedMapping, content_digest,
)
from aeep.assessment.planning import ReusableBuildOutput
from aeep.assessment.service import AssessmentService, benchmark_route
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import AssessmentBenchmarkCondition, BenchmarkSuite
from aeep.models import ExecutorKind, ExecutorSpec, new_id
from aeep.qualification import behavior_fingerprint
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


async def main():
    assert not (OUT / 'training-review.json').exists()
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    try:
        result = json.loads((OUT / 'builder-result.json').read_text())
        assert result['passed'] and result['proxy_restored']
        source = verification_source_digest(ROOT)
        assert source == result['source_digest']
        built = ReusableBuildOutput.model_validate(repo.get('reusable_build_output', result['operation_id']))
        assert built.source == (OUT / 'generated-source.py.txt').read_text()
        assert hashlib.sha256(built.source.encode()).hexdigest() == result['source_sha256']
        origin = AssessmentPlan.model_validate(repo.get('plan', 'plan_a26f0d5197c849ec86aed1b7d2969579'))
        training = [case for case in origin.suite.cases if case.split.value == 'training']
        assert len(training) == 28
        assert [content_digest(case.action.input) for case in training] == built.training_input_digests
        recipe = RecipeDefinition.model_validate(repo.get('recipe', origin.recipe_digest))
        assert recipe.extension is not None
        original_reference = recipe.extension.reference
        reference_source = (OUT.parent / 'edit-study-preparation/reference.py').read_text()
        assert original_reference.config['argv'][-1] == reference_source
        # Only the trusted reference's existing batch CLI is adapted to one case.
        wrapper = reference_source.split("if __name__ == '__main__':", 1)[0]
        wrapper += "print(json.dumps(transform(json.load(sys.stdin))))\n"
        baseline = original_reference.model_copy(deep=True)
        baseline.id = 'toolkit-edit-generated-training.reference'
        baseline.input_schema = recipe.input_schema
        baseline.output_schema = recipe.output_schema
        baseline.config = {
            **original_reference.config,
            'argv': ['python3', '-c', wrapper], 'argv_literal': True,
            'stdin_json': True, 'timeout_seconds': 30,
        }
        candidate = ExecutorSpec(
            id='toolkit-edit-generated-training.generated', capability=recipe.capability,
            kind=ExecutorKind.COMMAND, description='Frozen generated editing tool; training diagnostic only',
            input_schema=recipe.input_schema, output_schema=recipe.output_schema,
            config={'argv': ['python3', '-c', built.source], 'argv_literal': True,
                    'stdin_json': True, 'timeout_seconds': 30, 'max_output_bytes': 1000000,
                    'output': {'type': 'json'}},
        )
        candidate.estimate.cash = baseline.estimate.cash.model_copy(deep=True)
        for spec in (candidate, baseline):
            router.register(spec)
        subject = service.inspect_local(OUT / 'generated-source.py.txt', kind='command')
        environment = AssessmentEnvironment(
            environment_id='toolkit-edit-generated-training-20261019', kind='container',
            identity={'source_digest': source,
                      'purpose': 'Original 28 training inputs only; no materialization or qualification claim',
                      'origin_plan_digest': content_digest(origin)},
            container_image='sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228',
            container_runtime='/usr/local/bin/docker',
            container_socket='/Users/edwintse/.docker/run/docker.sock', memory_mb=512,
        )
        mapping = ReviewedMapping(candidate=candidate, baseline=baseline,
                                  executable_dependencies=runtime_dependencies())
        comparison = define('direct', candidate, baseline, [], None)
        definitions = {}

        def put(kind, value):
            digest = content_digest(value)
            repo.put(kind, digest, value)
            definitions[digest] = value.model_dump(mode='json')
            return digest

        subject_digest = content_digest(subject)
        definitions[subject_digest] = subject.model_dump(mode='json')
        recipe_digest = put('recipe', recipe)
        mapping_digest = put('mapping', mapping)
        environment_digest = put('environment', environment)
        comparison_digest = put('comparison', comparison)
        # This is a manually reviewed v2 training diagnostic, not a modified v3
        # generated campaign. Its inputs are the exact construction inputs. The
        # origin's materialized case set and qualification plan remain unchanged.
        plan = AssessmentPlan(
            schema_version='assessment.plan.v2', subject_digest=subject_digest,
            recipe_digest=recipe_digest, mapping_digest=mapping_digest,
            environment_digest=environment_digest, authorization_id='onboarding',
            candidate_id=candidate.id, baseline_id=baseline.id,
            definition_digests=[recipe_digest, mapping_digest, environment_digest, comparison_digest],
            route_fingerprints={spec.id: behavior_fingerprint(spec) for spec in mapping.subjects},
            executable_dependencies=mapping.executable_dependencies,
            suite=BenchmarkSuite(
                suite_id=new_id('training_suite'), domain=recipe.capability,
                deterministic_tools_available=True, seed=origin.suite.seed, repetitions=1,
                routes=[benchmark_route(spec) for spec in mapping.subjects],
                conditions=[AssessmentBenchmarkCondition.ROUTER_FRESH], cases=training,
                baseline_route_id=baseline.id, max_total_cash_usd=0,
                allow_zero_subscription_weight=True, sequential_stages=True, paired_order=True,
            ),
            applicability=origin.applicability, feature_combinations=origin.feature_combinations,
            planning_request_ids=[built.request_id], comparison=comparison,
        )
        repo.put('plan', plan.plan_id, plan)
        definitions[content_digest(plan)] = plan.model_dump(mode='json')
        service._verify_dependencies(plan)
        grant = AssessmentAuthorization.model_validate(repo.get('authorization', 'onboarding'))
        amendment = AssessmentScopeAmendment(
            authorization_id='onboarding', authorization_digest=content_digest(grant),
            subject_digests=[subject_digest], recipe_digests=[recipe_digest],
            environment_digests=[environment_digest], reviewed_digests=sorted(definitions),
        )
        review = {
            'authority': 'Inert preparation under standing definition delegation; execution awaits exact user approval',
            'source_digest': source, 'source_sha256': result['source_sha256'],
            'origin_plan_id': origin.plan_id, 'origin_plan_digest': content_digest(origin),
            'origin_case_set_digest': origin.recipe_case_set_digest,
            'build_operation_id': built.operation_id, 'training_input_digests': built.training_input_digests,
            'reference_wrapper_sha256': hashlib.sha256(wrapper.encode()).hexdigest(),
            'plan': plan.model_dump(mode='json'), 'definitions': definitions,
            'amendment': amendment.model_dump(mode='json'), 'budget_preview': service.budget_preview(plan.plan_id),
            'qualification': False, 'admission': False, 'generated_code_executed': False,
            'review_findings': [
                'Source read in full: io/json/sys/tokenize only; stdin/stdout data transformation, no file opening, network, subprocess, eval or dynamic imports.',
                'Usage requests Python 3.11. This experiment uses the already reviewed Python 3.13 image; record compatibility only for its bounded training cases, without a Python 3.11 compatibility claim.',
                'No source or grader repair after results. Preserve imperfect or failed training evidence. Reusable model arm remains optional.',
                'The original 28 construction inputs are reused intentionally. This manual v2 diagnostic does not alter the frozen qualification case set and cannot qualify or admit the tool.',
            ],
        }
        (OUT / 'training-review.json').write_text(json.dumps(review, indent=2) + '\n')
        print(json.dumps({'plan_id': plan.plan_id,
                          'allowance': review['budget_preview']['campaign_allowance'],
                          'generated_code_executed': False}))
    finally:
        await router.close()


asyncio.run(main())
