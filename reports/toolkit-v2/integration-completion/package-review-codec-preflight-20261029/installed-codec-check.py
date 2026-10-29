"""First-party installed-package fixture; no worker, source grader or model call."""
import json
import sys
from types import SimpleNamespace

from aeep.assessment.models import AssessmentPlan, AssessmentSubject, ReviewedMapping, content_digest
from aeep.assessment.repository_suites import require_worker_artifact_encoding
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkCase, BenchmarkSuite
from aeep.errors import ConfigurationError
from aeep.models import ActionRequest, ExecutorKind, ExecutorSpec, ValidationSpec
from aeep.qualification import behavior_fingerprint

CAPABILITY = 'assessment.repository_suite@1'


def case(encoding=None):
    return BenchmarkCase(case_id='fixture-' + str(encoding), split='training',
        action=ActionRequest(capability=CAPABILITY, input={'first_party_fixture': True}),
        validators=[ValidationSpec(kind='callback', config={'name': 'fixture',
            'expected': {} if encoding is None else {'patch_encoding': encoding}})])


def worker(name, field):
    return ExecutorSpec(id=name, capability=CAPABILITY, kind=ExecutorKind.MANAGED_HOST,
        description='First-party fixture; never executed.', resource_pool='fixture',
        config={'adapter_id': 'fixture', 'argv': [sys.executable],
            'instructions': 'Never executed.', 'managed_worker': {},
            'artifact': {'input_field': 'source_b64', 'output_field': field,
                'input_name': 'repository.tar.gz', 'output_name': 'patch.json'}})


for field, encoding in [('patch_b64', None), ('patch_gzip_b64', 'gzip-json')]:
    require_worker_artifact_encoding([case(encoding)], [worker('candidate', field), worker('baseline', field)])
    for cases in ([case('gzip-json' if encoding is None else None)], [case(), case('gzip-json')]):
        try:
            require_worker_artifact_encoding(cases, [worker('candidate', field)])
        except ConfigurationError as exc:
            assert 'patch encoding is incompatible' in str(exc)
        else:
            raise AssertionError('Incompatible standard artifact bridge accepted')

mapping = ReviewedMapping(candidate=worker('candidate', 'patch_gzip_b64'), baseline=worker('baseline', 'patch_gzip_b64'))
subject = AssessmentSubject(kind='skill', location='/never-opened/fixture', dependency_digests={})
suite = BenchmarkSuite(suite_id='installed-first-party-codec-fixture', domain=CAPABILITY,
    routes=[{'route_id': s.id, 'executor_id': s.id} for s in mapping.subjects],
    conditions=['fresh-worker'], cases=[case()], baseline_route_id='baseline')
plan = AssessmentPlan(subject_digest=content_digest(subject), recipe_digest='1' * 64,
    mapping_digest=content_digest(mapping), environment_digest='2' * 64,
    authorization_id='no-authority-fixture', candidate_id='candidate', baseline_id='baseline',
    suite=suite, definition_digests=[content_digest(subject), content_digest(mapping), '1' * 64, '2' * 64],
    applicability={'first_party_fixture': [True]},
    route_fingerprints={s.id: behavior_fingerprint(s) for s in mapping.subjects})
values = {'plan': plan.model_dump(mode='json'), 'mapping': mapping.model_dump(mode='json')}
service = object.__new__(AssessmentService)
service.repository = SimpleNamespace(get=lambda kind, _identity: values[kind])
# No grant store or router exists. Accessing either would fail this fixture.
try:
    service.budget_preview(plan.plan_id)
except ConfigurationError as exc:
    assert 'patch encoding is incompatible' in str(exc)
else:
    raise AssertionError('Budget preview accepted incompatible standard bridge')
print(json.dumps({'matching_profiles_accepted': 2, 'incompatible_profiles_rejected': 4,
    'budget_preview_rejected_before_grant_or_router': True, 'model_calls': 0,
    'external_source_execution': False, 'fixture_only': True}))
