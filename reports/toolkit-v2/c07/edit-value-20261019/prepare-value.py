"""Freeze the existing four-arm experiment after canonical qualification passes."""
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.boundary import require_differential, require_managed_boundaries
from aeep.assessment.comparison import arm
from aeep.assessment.extensions import materialize, prepare
from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentEnvironment, AssessmentPlan, AssessmentReport,
    AssessmentScopeAmendment, AssessmentSubject, IncrementalExperiment,
    RecipeDefinition, ReusableBaselineArtifact, content_digest,
)
from aeep.assessment.planning import ReusableBuildOutput
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from aeep.qualification import behavior_fingerprint
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def read(folder, name):
    return json.loads((OUT.parent / folder / name).read_text())


async def main():
    assert not (OUT / 'value-review.json').exists()
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    try:
        source = verification_source_digest(ROOT)
        qualified = read('edit-study-prompt-20261019', 'qualification-result.json')
        assert qualified['qualification_passed'] and qualified['proxy_restored']
        assert qualified['source_unchanged'] and qualified['source_digest'] == source
        qualification = AssessmentReport.model_validate(repo.get('report', qualified['report_id']))
        origin = AssessmentPlan.model_validate(repo.get('plan', qualification.plan_digest))
        service_status = service.status(qualified['assessment_id'])
        assert service_status['state'] == 'complete' and service_status['error_code'] is None
        assert origin.comparison and origin.comparison.experiment
        recipe = RecipeDefinition.model_validate(repo.get('recipe', origin.recipe_digest))
        subject = AssessmentSubject.model_validate(repo.get('subject', origin.subject_digest))
        pair_review = json.loads((OUT / 'pair-review.json').read_text())
        pair = pair_review['definitions'][pair_review['pair_definition_digest']]
        boundary = json.loads((OUT / 'boundary-result.json').read_text())
        specs = [ExecutorSpec.model_validate(pair[role]) for role in ('control', 'treatment')]
        assert pair['differential'] == origin.comparison.experiment.environment.model_dump(mode='json')
        helpers = []
        conformance = {spec.id: boundary['boundaries'][role]['conformance_digest']
                       for spec, role in zip(specs, ('control', 'treatment'), strict=True)}
        identities = {spec.id: boundary['boundaries'][role]['identity_digest']
                      for spec, role in zip(specs, ('control', 'treatment'), strict=True)}
        for folder in ('edit-higher-20261019', 'edit-reusable-pair-20261019'):
            review = read(folder, 'pair-review.json')
            definition = review['definitions'][review['pair_definition_digest']]
            observed = read(folder, 'boundary-result.json')
            terminal = read(folder, 'pair-result.json')
            assert terminal['paired_checks_passed'] and terminal['proxy_restored_stopped']
            assert terminal['source_unchanged'] and observed['source_digest'] == source
            spec = ExecutorSpec.model_validate(definition['control'])
            helpers.append(spec)
            conformance[spec.id] = observed['boundaries']['control']['conformance_digest']
            identities[spec.id] = observed['boundaries']['control']['identity_digest']
        assert len({spec.config['managed_worker']['worker_id'] for spec in [*specs, *helpers]}) == 4
        assert all(spec.config['instructions'] == specs[0].config['instructions'] for spec in [*specs, *helpers])
        assert specs[1].config['invocation']['exposure'] == 'optional'
        for spec in [*specs, *helpers]:
            assert spec.config['adapter_options']['output_schema_mode'] == 'prompt'
            router.register(spec)
        environment = AssessmentEnvironment(
            environment_id='toolkit-edit-value-20261019-' + source[:12], kind='container',
            identity={'source_digest': source, 'purpose': 'Frozen optional-use four-arm editing comparison'},
            container_image='sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228',
            container_runtime='/usr/local/bin/docker', container_socket='/Users/edwintse/.docker/run/docker.sock',
            memory_mb=512, conformance_digests=conformance,
            differential_conformance_digest=boundary['differential_conformance_digest'],
        )
        build = read('edit-reusable-20261019', 'builder-result.json')
        built = ReusableBuildOutput.model_validate(repo.get('reusable_build_output', build['operation_id']))
        images = read('edit-reusable-20261019', 'images-readable-accounted-result.json')
        assert images['passed'] and images['source_unchanged']
        assert hashlib.sha256(built.source.encode()).hexdigest() == images['files']['/opt/dependencies/reusable/tool.py']
        assert helpers[1].config['managed_worker']['image'] == images['images']['control']
        artifact = ReusableBaselineArtifact(
            executor_fingerprint=behavior_fingerprint(helpers[1]), worker_files=images['files'],
            training_input_digests=built.training_input_digests, build_operation_ids=[built.operation_id],
        )
        artifact_digest = repo.put('reusable_baseline', content_digest(artifact), artifact)
        artifact_review = {
            'authority': 'Exact artifact binding under September25/27 definition delegation after explicit source/image approvals',
            'source_execution_approval_sha256': 'dbc2dda63cff7586a0a0d9a699021085e1b9b4c9f619c54a54d90da7047d6d4b',
            'image_permission_approval_sha256': '1484c3ba6b748d740c28107fe88b179b3fe4b0a0d5022991079fcd71ced3bd15',
            'artifact_digest': artifact_digest, 'artifact': artifact.model_dump(mode='json'),
            'worker_image': images['images']['control'], 'source_digest': source,
        }
        (OUT / 'reusable-artifact-review.json').write_text(json.dumps(artifact_review, indent=2) + '\n')
        repo.review(artifact_digest)
        request = prepare(service, subject_id=subject.subject_id, recipe_id=origin.recipe_digest,
                          authorization_id='onboarding', environment=environment, seed=2026101904)
        grant = AssessmentAuthorization.model_validate(repo.get('authorization', 'onboarding'))

        def bundle(digests, plan_subject, plan_recipe, plan_environment):
            documents = {d: json.loads(router.store._connection.execute(
                'SELECT payload_json FROM assessment_records WHERE digest=?', (d,)).fetchone()[0]) for d in digests}
            amendment = AssessmentScopeAmendment(
                authorization_id='onboarding', authorization_digest=content_digest(grant),
                subject_digests=[plan_subject], recipe_digests=[plan_recipe],
                environment_digests=[plan_environment], reviewed_digests=sorted(digests))
            return documents, amendment

        ds = set(request.definition_digests) | {request.subject_digest, content_digest(request), artifact_digest}
        documents, amendment = bundle(ds, request.subject_digest, request.recipe_digest, request.environment_digest)
        case_review = {'authority': 'Standing first-party fixture generation and finite definition delegation',
                       'request': request.model_dump(mode='json'), 'definitions': documents,
                       'amendment': amendment.model_dump(mode='json'), 'maximum_model_turns': 0,
                       'maximum_operations': 1, 'maximum_seconds': 20, 'cash_usd': 0}
        (OUT / 'case-materialization-review.json').write_text(json.dumps(case_review, indent=2) + '\n')
        repo.approve_bundle(amendment, documents)
        cases = await materialize(service, request.plan_id)
        prior_inputs = set()
        for identity in (origin.plan_id, 'plan_16fb057af234452e91214c6829348d29', 'plan_0a8359a155184098ad3ba790f8a77f55'):
            previous = AssessmentPlan.model_validate(repo.get('plan', identity))
            prior_inputs.update(content_digest(case.action.input) for case in previous.suite.cases)
        assert len(cases.cases) == 141
        assert not prior_inputs.intersection(content_digest(case.action.input) for case in cases.cases)
        experiment = IncrementalExperiment(
            stage='marginal_value', exposure='optional', environment=pair['differential'],
            utility=origin.comparison.experiment.utility,
            higher_compute=arm(helpers[0], []), reusable_tool=arm(helpers[1], []),
            reusable_artifact_digest=artifact_digest, reusable_build_operation_ids=[built.operation_id],
            feasible_challengers=[item.id for item in helpers], qualification_report_digest=content_digest(qualification),
        )
        plan = service.propose(
            subject_id=subject.subject_id, family=origin.recipe_digest, candidate_id=specs[1].id,
            baseline_id=specs[0].id, authorization_id='onboarding', environment=environment,
            seed=2026101904, case_set_id=request.plan_id, structure='controlled_agent', experiment=experiment,
        )
        assert not plan.blocked_reasons
        require_managed_boundaries(repo, environment, [*specs, *helpers], identities)
        require_differential(repo, environment, plan)
        service._verify_dependencies(plan)
        ds = set(plan.definition_digests) | {plan.subject_digest, content_digest(plan), artifact_digest}
        documents, amendment = bundle(ds, plan.subject_digest, plan.recipe_digest, plan.environment_digest)
        review = {
            'authority': 'Standing exact finite definition delegation plus recorded generated-source/image approvals',
            'source_digest': source, 'plan_id': plan.plan_id, 'plan_digest': content_digest(plan),
            'definitions': documents, 'amendment': amendment.model_dump(mode='json'),
            'budget_preview': service.budget_preview(plan.plan_id), 'blocked_reasons': plan.blocked_reasons,
            'preregistration_sha256': hashlib.sha256((OUT / 'preregistration.json').read_bytes()).hexdigest(),
            'qualification_report_id': qualification.report_id, 'value_seed': 2026101904,
            'fresh_cases_disjoint': True, 'not_enqueued': True, 'admission': False,
            'extra_study_setup_costs': 'Export a separate canonical operation ledger for the training campaign, image operations, readiness diagnoses and failed predecessors; do not present the campaign-only cost ledger as all project spending.',
        }
        (OUT / 'value-review.json').write_text(json.dumps(review, indent=2) + '\n')
        print(json.dumps({'plan_id': plan.plan_id, 'blocked_reasons': plan.blocked_reasons,
                          'upper_allowance': review['budget_preview']['campaign_allowance']['upper_allowance'],
                          'not_enqueued': True}))
    finally:
        await router.close()


asyncio.run(main())
