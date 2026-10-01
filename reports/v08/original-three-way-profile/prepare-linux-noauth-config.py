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
SOURCE = '94f3fad31d2811368a2955a63b0531b5147f0d132551000f674292b7a5a280bb'
assert verification_source_digest(ROOT) == SOURCE
assert not (OUT / 'linux-noauth-config-review.json').exists()
prior = json.loads((ROOT / 'reports/v08/worker1592-successor/conformance-46803-review.json').read_text())
programs = {'outside_mcp': (OUT / 'linux-mcp-server.py').read_text()}
router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
repo = service.repository
try:
    pair = repo.get('worker_pair_definition', prior['pair_definition_digest'])
    import copy
    profiles = {'outside_mcp': copy.deepcopy(pair['control'])}
    setup=json.loads((OUT/'linux-image-successor-result.json').read_text())
    assert setup['setup_complete'] and setup['source_unchanged'] and setup['inspection_cleanup_confirmed']
    canonical_setup=repo.get('linux_diagnostic_image_observation',setup['canonical_record_digest'])['facts']
    assert canonical_setup['image']==setup['image'] and canonical_setup['public_file_sha256']==setup['public_file_sha256']
    worker=profiles['outside_mcp']['config']['managed_worker']
    worker['image']=setup['image']
    worker['worker_id']='linux-noauth-config-diagnostic'
    worker['credential_volume']=None
    worker['network_id']=None
    worker['model_proxy_url']=None
    worker.setdefault('reviewed_files',{})['/opt/aeep/linux-mcp-server.py']=setup['public_file_sha256']['/opt/aeep/linux-mcp-server.py']
    import tomllib
    filesystem=tomllib.loads((OUT/'immutable-diagnostic/requirements.toml').read_text())['permissions']['aeep']['filesystem']
    inline='{'+', '.join(json.dumps(k)+' = '+json.dumps(v) for k,v in filesystem.items())+'}'
    assert tomllib.loads('x='+inline)['x']==filesystem
    profiles['outside_mcp']['config']['argv'].extend(['-c', 'permissions.aeep.filesystem='+inline, '-c', 'mcp_servers.linux_boundary_diagnostic.command="/usr/local/bin/python3"', '-c', 'mcp_servers.linux_boundary_diagnostic.args=["/opt/aeep/linux-mcp-server.py"]', '-c', 'mcp_servers.linux_boundary_diagnostic.enabled=true'])

    definition = Definition(source_digest=SOURCE, profiles=profiles, programs=programs,
        expected={'outside_mcp': {'sandbox_child_denied': True, 'model_command_denied': True, 'independent_canary_unchanged': True}})
    definition.programs['direct'] = 'import json,pathlib; r={}\nfor label,name in [("canary","/workspace/private-state.json"),("server","/opt/aeep/linux-mcp-server.py"),("requirements","/etc/codex/requirements.toml"),("config","/opt/aeep/worker-config.json")]:\n for op in ("read","write"):\n  try:\n   p=pathlib.Path(name);p.read_bytes() if op=="read" else p.write_bytes(b"changed");r[label+"_"+op+"_denied"]=False\n  except OSError:r[label+"_"+op+"_denied"]=True\nprint(json.dumps(r))'
    digest = content_digest(definition)
    definitions = {digest: definition}
    requests = []
    dependencies = runtime_dependencies()
    for filename in ('linux-mcp-server.py',):
        dependencies[str(OUT / filename)] = hashlib.sha256((OUT / filename).read_bytes()).hexdigest()
    dependencies[str(OUT / 'run-linux-noauth-config.py')] = hashlib.sha256((OUT / 'run-linux-noauth-config.py').read_bytes()).hexdigest()
    for source in (prior['requests'][0],):
        request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2', operation='worker_inspection',
            subject_digest=source['subject_digest'], recipe_digest=source['recipe_digest'],
            mapping_digest=digest, environment_digest=source['environment_digest'],
            authorization_id='onboarding', definition_digests=[digest, source['recipe_digest'], source['environment_digest']],
            worker_digest=__import__('aeep.hosts.workers',fromlist=['binding_from_config']).binding_from_config(worker).digest(), executable_dependencies=dependencies)
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
        'timeout_accounting': {'body_seconds': 30, 'transport_close_seconds': 3, 'worker_cleanup_seconds': 8, 'remaining_overhead_seconds_per_operation': 19}, 'applicability': 'Actual MCP startup child launches fixed sandbox diagnostic; synthetic canary observations only, no production store or full conformance claim.', 'not_full_conformance': True, 'no_model_or_workbook_trial': True, 'configuration_only':True, 'no_auth_volume_or_account_login_methods':True, 'second_only_after_first_support': False, 'execution_authorized': False, 'setup_canonical_record_digest':setup['canonical_record_digest'], 'protected_file_sha256':setup['public_file_sha256'], 'effective_requirements_expected':{'allowedPermissionProfiles':{'aeep':True},'allowedApprovalPolicies':['never']}, 'tool_digest': __import__('aeep.hosts.codex_invocation', fromlist=['contract_digest']).contract_digest({'name': 'sandbox_probe', 'description': 'Observe a fixed synthetic Linux sandbox boundary.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}), 'direct_program': 'import json,pathlib;p=pathlib.Path("/workspace/private-state.json");r={};\nfor op in ("read","write"):\n try:\n  p.read_bytes() if op=="read" else p.write_bytes(b"changed");r[op+"_denied"]=False\n except OSError:r[op+"_denied"]=True\nprint(json.dumps(r))', 'qualification': False, 'no_private_mcp_placement_claim': True, 'no_image_change_or_auth_access': True}
    (OUT / 'linux-noauth-config-review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({'request_ids': [r.plan_id for r in requests], 'review_sha256': hashlib.sha256((OUT / 'linux-noauth-config-review.json').read_bytes()).hexdigest(), 'inert': True}))
finally:
    router.store.close()
