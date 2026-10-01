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
    maximum_operations: int = 1
    maximum_reserved_seconds: int = 60
    maximum_model_turns: int = 0


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SOURCE = '46803ee2814c77977c4408b60768c6581fc0189f0c8fb9a8ccd7dd77ccc4b236'
assert verification_source_digest(ROOT) == SOURCE
assert not (OUT / 'linux-mcp-successor-review.json').exists()
prior = json.loads((ROOT / 'reports/v08/worker1592-successor/conformance-46803-review.json').read_text())
programs = {'outside_mcp': (OUT / 'linux-mcp-server.py').read_text()}
router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
repo = service.repository
try:
    pair = repo.get('worker_pair_definition', prior['pair_definition_digest'])
    import copy
    profiles = {'outside_mcp': copy.deepcopy(pair['control'])}
    profiles['outside_mcp']['config']['argv'].extend(['-c', 'permissions.aeep.filesystem."/workspace/private-state.json"="deny"', '-c', 'mcp_servers.linux_boundary_diagnostic.command="python3"', '-c', 'mcp_servers.linux_boundary_diagnostic.args=' + json.dumps(['-c', programs['outside_mcp']]), '-c', 'mcp_servers.linux_boundary_diagnostic.enabled=true'])
    definition = Definition(source_digest=SOURCE, profiles=profiles, programs=programs,
        expected={'outside_mcp': {'sandbox_child_denied': True, 'model_command_denied': True, 'independent_canary_unchanged': True}})
    definition.programs['direct'] = 'import json,pathlib;p=pathlib.Path("/workspace/private-state.json");r={};\nfor op in ("read","write"):\n try:\n  p.read_bytes() if op=="read" else p.write_bytes(b"changed");r[op+"_denied"]=False\n except OSError:r[op+"_denied"]=True\nprint(json.dumps(r))'
    digest = content_digest(definition)
    definitions = {digest: definition}
    requests = []
    dependencies = runtime_dependencies()
    for filename in ('linux-mcp-server.py',):
        dependencies[str(OUT / filename)] = hashlib.sha256((OUT / filename).read_bytes()).hexdigest()
    dependencies[str(OUT / 'run-linux-mcp-successor.py')] = hashlib.sha256((OUT / 'run-linux-mcp-successor.py').read_bytes()).hexdigest()
    for source in (prior['requests'][0],):
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
    review = {'authority': 'Standing finite assessment amendments; parent authorized exact zero-model MCP startup Linux sandbox availability/denial after queued work',
        'source_digest': SOURCE, 'definition_digest': digest, 'definition': definition.model_dump(mode='json'),
        'requests': [r.model_dump(mode='json') for r in requests], 'amendment': amendment.model_dump(mode='json'),
        'definitions': {d: o.model_dump(mode='json') if hasattr(o, 'model_dump') else o for d, o in definitions.items()},
        'maximum_operations': 1, 'maximum_reserved_seconds': 60, 'maximum_model_turns': 0, 'cash_usd': 0,
        'timeout_accounting': {'body_seconds': 40, 'transport_close_seconds': 3, 'worker_cleanup_seconds': 8, 'remaining_overhead_seconds_per_operation': 9}, 'applicability': 'Actual MCP startup child launches fixed sandbox diagnostic; synthetic canary observations only, no production store or full conformance claim.', 'not_full_conformance': True, 'no_model_or_workbook_trial': True, 'second_only_after_first_support': False, 'execution_authorized': False, 'tool_digest': __import__('aeep.hosts.codex_invocation', fromlist=['contract_digest']).contract_digest({'name': 'sandbox_probe', 'description': 'Observe a fixed synthetic Linux sandbox boundary.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}), 'direct_program': 'import json,pathlib;p=pathlib.Path("/workspace/private-state.json");r={};\nfor op in ("read","write"):\n try:\n  p.read_bytes() if op=="read" else p.write_bytes(b"changed");r[op+"_denied"]=False\n except OSError:r[op+"_denied"]=True\nprint(json.dumps(r))', 'qualification': False, 'no_private_mcp_placement_claim': True, 'no_image_change_or_auth_access': True}
    (OUT / 'linux-mcp-successor-review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({'request_ids': [r.plan_id for r in requests], 'review_sha256': hashlib.sha256((OUT / 'linux-mcp-successor-review.json').read_bytes()).hexdigest(), 'inert': True}))
finally:
    router.store.close()
