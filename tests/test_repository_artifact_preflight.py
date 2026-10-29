"""First-party definition regressions; no workers, models or benchmark evidence."""
import sys
from types import SimpleNamespace

import pytest

from aeep.assessment.models import (
    AssessmentPlan,
    AssessmentSubject,
    ReviewedMapping,
    content_digest,
)
from aeep.assessment.repository_suites import require_worker_artifact_encoding
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkCase, BenchmarkSuite
from aeep.errors import ConfigurationError
from aeep.models import ActionRequest, ExecutorKind, ExecutorSpec, ValidationSpec
from aeep.qualification import behavior_fingerprint

pytestmark = pytest.mark.assessment_contract
CAPABILITY = 'assessment.repository_suite@1'


def case(encoding=None, *, capability=CAPABILITY):
    truth = {} if encoding is None else {'patch_encoding': encoding}
    return BenchmarkCase(case_id='fixture-' + str(encoding), split='training',
        action=ActionRequest(capability=capability, input={'first_party_fixture': True}),
        validators=[ValidationSpec(kind='callback', config={'name': 'fixture', 'expected': truth})])


def worker(name, field):
    config = {'adapter_id': 'fixture', 'argv': [sys.executable], 'instructions': 'Never executed.', 'managed_worker': {}}
    if field is not None:
        config['artifact'] = {'input_field': 'source_b64', 'output_field': field,
            'input_name': 'repository.tar.gz', 'output_name': 'patch.json'}
    return ExecutorSpec(id=name, capability=CAPABILITY, kind=ExecutorKind.MANAGED_HOST,
        description='First-party fixture; never executed.', resource_pool='fixture', config=config)


@pytest.mark.parametrize(('field', 'encoding'), [('patch_b64', None), ('patch_gzip_b64', 'gzip-json')])
def test_matching_standard_bridge_is_accepted(field, encoding):
    require_worker_artifact_encoding([case(encoding)], [worker('candidate', field), worker('baseline', field)])


@pytest.mark.parametrize(('candidate', 'baseline'), [
    ('patch_gzip_b64', 'patch_b64'), ('patch_b64', 'patch_gzip_b64'), ('patch_gzip_b64', 'patch_gzip_b64')])
def test_mismatched_bridge_in_either_arm_is_rejected(candidate, baseline):
    with pytest.raises(ConfigurationError, match='patch encoding is incompatible'):
        require_worker_artifact_encoding([case()], [worker('candidate', candidate), worker('baseline', baseline)])


@pytest.mark.parametrize('field', ['patch_b64', 'patch_gzip_b64'])
def test_mixed_codecs_need_separate_static_worker_profiles(field):
    with pytest.raises(ConfigurationError, match='separate matching'):
        require_worker_artifact_encoding([case(), case('gzip-json')], [worker('candidate', field)])


def test_other_capabilities_direct_outputs_and_custom_bridges_keep_existing_contracts():
    require_worker_artifact_encoding([case(capability='fixture.other@1')], [worker('candidate', 'patch_gzip_b64')])
    require_worker_artifact_encoding([case()], [worker('candidate', None), worker('custom', 'reviewed_custom_field')])
    command = ExecutorSpec(id='command', capability=CAPABILITY, kind='command',
        description='First-party fixture; never executed.', config={'argv': [sys.executable]})
    require_worker_artifact_encoding([case()], [command])


@pytest.mark.parametrize('truth', [None, {'patch_encoding': 'unsupported'}])
def test_missing_or_unsupported_encoding_truth_fails_before_work(truth):
    value = case()
    value.validators[0].config['expected'] = truth
    with pytest.raises(ConfigurationError, match='supported patch-encoding truth'):
        require_worker_artifact_encoding([value], [worker('candidate', 'patch_b64')])
    value.validators = []
    with pytest.raises(ConfigurationError, match='supported patch-encoding truth'):
        require_worker_artifact_encoding([value], [worker('candidate', 'patch_b64')])


def test_budget_and_dispatch_preflight_reject_before_grant_or_router_use(monkeypatch):
    from aeep.assessment import pilot
    from aeep.assessment import service as service_module
    mapping = ReviewedMapping(candidate=worker('candidate', 'patch_gzip_b64'), baseline=worker('baseline', 'patch_gzip_b64'))
    suite = BenchmarkSuite(suite_id='first-party-preflight-fixture', domain=CAPABILITY,
        routes=[{'route_id': spec.id, 'executor_id': spec.id} for spec in mapping.subjects],
        conditions=['fresh-worker'], cases=[case()], baseline_route_id='baseline')
    subject = AssessmentSubject(kind='skill', location='/never-opened/fixture', dependency_digests={})
    plan = AssessmentPlan(subject_digest=content_digest(subject), recipe_digest='1' * 64,
        mapping_digest=content_digest(mapping), environment_digest='2' * 64, authorization_id='no-authority-fixture',
        candidate_id='candidate', baseline_id='baseline', suite=suite,
        definition_digests=[content_digest(subject), content_digest(mapping), '1' * 64, '2' * 64],
        applicability={'first_party_fixture': [True]},
        route_fingerprints={spec.id: behavior_fingerprint(spec) for spec in mapping.subjects})
    values = {'plan': plan.model_dump(mode='json'), 'mapping': mapping.model_dump(mode='json'),
              'subject': subject.model_dump(mode='json')}
    assessment = object.__new__(AssessmentService)
    assessment.repository = SimpleNamespace(get=lambda kind, _identity: values[kind])
    # No router or grant store exists: an attempted reservation/dispatch cannot hide a bad preflight.
    with pytest.raises(ConfigurationError, match='patch encoding is incompatible'):
        assessment.budget_preview(plan.plan_id)
    monkeypatch.setattr(pilot, 'require_separation', lambda *args: None)
    monkeypatch.setattr(pilot, 'require_linked_pilot', lambda *args: None)
    monkeypatch.setattr(service_module, 'verify_subject', lambda *args: None)
    with pytest.raises(ConfigurationError, match='patch encoding is incompatible'):
        assessment._verify_dependencies(plan)
