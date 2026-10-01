"""Prepare only: exact zero-model supplementary helper inspection on successor workers."""
import hashlib
import json
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentAuthorization, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel
from aeep.router import Router


class Definition(StrictModel):
    source_digest: str
    profiles: dict
    programs: dict
    expected: dict
    maximum_operations: int = 2
    maximum_reserved_seconds: int = 90
    maximum_model_turns: int = 0


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SOURCE = '46803ee2814c77977c4408b60768c6581fc0189f0c8fb9a8ccd7dd77ccc4b236'
assert verification_source_digest(ROOT) == SOURCE
assert not (OUT / 'linux-probe-review.json').exists()
prior = json.loads((ROOT / 'reports/v08/worker1592-successor/conformance-46803-review.json').read_text())
programs = {role: (OUT / filename).read_text() for role, filename in [('availability', 'linux-availability-program.py'), ('denial', 'linux-denial-program.py')]}
router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
repo = service.repository
try:
    pair = repo.get('worker_pair_definition', prior['pair_definition_digest'])
    import copy
    profiles = {role: copy.deepcopy(pair['control']) for role in ('availability', 'denial')}
    profiles['denial']['config']['argv'].extend(['-c', 'permissions.aeep.filesystem."/workspace/private-state.json"="deny"'])
    definition = Definition(source_digest=SOURCE, profiles=profiles, programs=programs,
        expected={'availability': {'nested_supported': True}, 'denial': {'read_denied': True, 'write_denied': True, 'nested_read_denied': True, 'nested_write_denied': True, 'canary_unchanged': True}})
    digest = content_digest(definition)
    definitions = {digest: definition}
    requests = []
    dependencies = runtime_dependencies()
    for filename in ('linux-availability-program.py', 'linux-denial-program.py'):
        dependencies[str(OUT / filename)] = hashlib.sha256((OUT / filename).read_bytes()).hexdigest()
    dependencies[str(OUT / 'run-linux-probe.py')] = hashlib.sha256((OUT / 'run-linux-probe.py').read_bytes()).hexdigest()
    for source in (prior['requests'][0], prior['requests'][0]):
        request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2', operation='worker_inspection',
            subject_digest=source['subject_digest'], recipe_digest=source['recipe_digest'],
            mapping_digest=digest, environment_digest=source['environment_digest'],
            authorization_id='onboarding', definition_digests=[digest, source['recipe_digest'], source['environment_digest']],
            worker_digest=source['worker_digest'], executable_dependencies=dependencies)
        repo.put('conformance_request', request.plan_id, request)
        definitions[content_digest(request)] = request
        for kind, key in [('subject', 'subject_digest'), ('recipe', 'recipe_digest'), ('environment', 'environment_digest')]:
            definitions[source[key]] = repo.get(kind, source[key])
        requests.append(request)
    repo.put('linux_task_probe_definition', digest, definition)
    grant = AssessmentAuthorization.model_validate(repo.get('authorization', 'onboarding'))
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=content_digest(grant),
        subject_digests=list({r.subject_digest for r in requests}), recipe_digests=list({r.recipe_digest for r in requests}),
        environment_digests=list({r.environment_digest for r in requests}), reviewed_digests=list(definitions))
    review = {'authority': 'Standing finite assessment amendments; parent authorized exact zero-model nested Linux sandbox availability/denial after queued work',
        'source_digest': SOURCE, 'definition_digest': digest, 'definition': definition.model_dump(mode='json'),
        'requests': [r.model_dump(mode='json') for r in requests], 'amendment': amendment.model_dump(mode='json'),
        'definitions': {d: o.model_dump(mode='json') if hasattr(o, 'model_dump') else o for d, o in definitions.items()},
        'maximum_operations': 2, 'maximum_reserved_seconds': 90, 'maximum_model_turns': 0, 'cash_usd': 0,
        'timeout_accounting': {'body_seconds': 25, 'transport_close_seconds': 3, 'worker_cleanup_seconds': 8, 'remaining_overhead_seconds_per_operation': 9}, 'applicability': 'Nested sandbox inside the existing model-command sandbox only. Failure does not establish whether an MCP process outside that sandbox can launch an isolated task child.', 'not_full_conformance': True, 'no_model_or_workbook_trial': True, 'second_only_after_first_support': True, 'execution_authorized': False, 'qualification': False, 'no_private_mcp_placement_claim': True, 'no_image_change_or_auth_access': True}
    (OUT / 'linux-probe-review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({'request_ids': [r.plan_id for r in requests], 'review_sha256': hashlib.sha256((OUT / 'linux-probe-review.json').read_bytes()).hexdigest(), 'inert': True}))
finally:
    router.store.close()
