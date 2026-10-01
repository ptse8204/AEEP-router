"""Inert until exact review hash supplied; supplementary inspection, never a model trial."""
import asyncio
import hashlib
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, StrictModel
from aeep.router import Router


class Definition(StrictModel):
    source_digest: str
    profiles: dict
    thread_start_params: dict
    expected_permissions: dict
    maximum_operations: int
    maximum_reserved_seconds: int
    maximum_model_turns: int


class Result(StrictModel):
    facts: dict


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent


def safe_transport_facts(adapter, exc=None):
    facts = {}
    chain = []
    while exc is not None and len(chain) < 4:
        chain.append(exc)
        exc = exc.__cause__
    templates = {'Codex App Server transport failed': 'transport_failed', 'malformed App Server frame': 'malformed_frame', 'App Server frame must be an object': 'invalid_frame_type', 'App Server result must be an object': 'invalid_result_type', 'App Server version differs from the reviewed protocol binding': 'version_mismatch', 'oversized App Server frame': 'oversized_frame'}
    import re
    for error in chain:
        data = getattr(error, 'error', None)
        if isinstance(data, dict) and isinstance(data.get('code'), int) and not isinstance(data['code'], bool):
            facts['json_rpc_error_code'] = data['code']
            message = data.get('message', '')
        else:
            message = str(error)
        if message in templates:
            facts['known_error_template'] = templates[message]
        match = re.fullmatch(r'Codex App Server exited with status (-?\d+)', message)
        if match:
            facts['known_error_template'] = 'process_exited'
            facts['reported_exit_code'] = int(match.group(1))
    if adapter is not None:
        transport = adapter.transport
        process = transport._process
        facts['process_exit_code_before_cleanup'] = process.returncode if process else None
        data = bytes(transport.stderr)
        text = data.decode('utf-8', errors='replace').lower()
        classes = (('unsupported_flag', ('unexpected argument', 'unrecognized option', 'unknown option')), ('permission_denied', ('permission denied', 'operation not permitted')), ('missing_path', ('no such file or directory', 'does not exist')), ('invalid_permission_profile', ('invalid permission', 'invalid filesystem', 'permission profile')), ('invalid_configuration', ('error loading configuration', 'failed to load config', 'invalid configuration')), ('namespace_unavailable', ('namespace', 'unshare')), ('seccomp_unavailable', ('seccomp',)), ('landlock_unavailable', ('landlock',)), ('bwrap_unavailable', ('bwrap', 'bubblewrap')))
        facts['config_error_categories']=[name for name,marker in [('untagged_enum_mismatch','did not match any variant of untagged enum'),('invalid_type','invalid type'),('invalid_value','invalid value'),('missing_field','missing field'),('unknown_field','unknown field'),('toml_parse','toml parse error'),('override_parse','error parsing'),('requirements_rejection','disallowed by requirements')] if marker in text]
        fields=('permissions','aeep','filesystem','mcp_servers','linux_boundary_diagnostic','command','args','identity','executable','value','match')
        facts['recognized_public_config_fields']=[field for field in fields if re.search(r'(?<![a-z_])'+re.escape(field)+r'(?![a-z_])',text)]
        facts['recognized_error_types']=[kind for kind in ('map','string','sequence','integer','boolean','enum','struct','table') if re.search(r'\b'+kind+r'\b',text)]
        enum_match=re.search(r'untagged enum ([A-Za-z_][A-Za-z0-9_]*)',data.decode('utf-8',errors='replace'))
        known_enums={'FilesystemPermissionEntryToml','PermissionsFilesystemEntryToml','McpServerIdentity','RawMcpServerIdentity','RawMcpServerConfig','McpServerRequirement','PermissionProfileToml','FeatureToml','PluginConfigToml'}
        if enum_match and enum_match.group(1) in known_enums:facts['known_config_enum']=enum_match.group(1)
        facts['stderr_class'] = next((name for name, markers in classes if any(marker in text for marker in markers)), 'unclassified' if data else 'none')
        facts['error_excerpt_withheld']='categorized_diagnostics_only'
        facts['stderr_bytes_retained'] = len(data)
        facts['stderr_truncated'] = transport.stderr_truncated
    return facts


def config_snapshot(response, expected):
    config = response.get('config')
    assert isinstance(config, dict), 'config snapshot unavailable'
    permissions = config.get('permissions')
    assert permissions is None or isinstance(permissions, dict), 'invalid permissions snapshot shape'
    facts = {'config_permissions_shape': 'null_or_absent' if permissions is None else 'object',
             'permission_filesystem_snapshot': 'unknown_managed_profile' if permissions is None else 'checked'}
    if permissions is not None:
        profile = permissions.get('aeep')
        assert isinstance(profile, dict) and profile.get('filesystem') == expected['aeep']['filesystem'] and profile.get('extends') is None, 'config-defined profile differs'
    servers = config.get('mcp_servers')
    assert isinstance(servers, dict), 'MCP snapshot unavailable'
    own = servers.get('linux_boundary_diagnostic')
    assert isinstance(own, dict) and own.get('enabled') is True, 'fixed MCP disabled or unavailable'
    assert own.get('command') == '/usr/local/bin/python3' and own.get('args') == ['/opt/aeep/linux-mcp-server.py'], 'fixed MCP identity differs'
    facts['permitted_fixed_mcp_startup'] = True
    return facts


async def main():
    path = OUT / 'linux-dynamic-tools-ack-managed-review.json'
    assert len(sys.argv) == 2 and hashlib.sha256(path.read_bytes()).hexdigest() == sys.argv[1]
    review = json.loads(path.read_text())
    assert review['execution_authorized'] is True
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == review['driver_sha256']
    validation = json.loads((ROOT / review['validation_record']).read_text())
    assert validation['source_digest'] == review['source_digest'] and validation['complete'] is True
    assert len(validation['checks']) >= 22 and all(x['exit_code'] == 0 for x in validation['checks'])
    assert verification_source_digest(ROOT) == review['source_digest']
    assert not (OUT / 'linux-dynamic-tools-ack-managed-result.json').exists()
    router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
    repo = service.repository
    result = {'source_digest': review['source_digest'], 'model_turns': 0, 'full_conformance': False, 'workers': {}}
    result['grant_before'] = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone()))
    (OUT / 'linux-dynamic-tools-ack-managed-grant-before.json').write_text(json.dumps({'source_digest': review['source_digest'], 'grant_before': result['grant_before'], 'review_sha256': sys.argv[1]}, indent=2) + '\n')
    try:
        definition = Definition.model_validate(review['definition'])
        assert definition.model_dump(mode='json') == review['definition']
        repo.put('linux_task_probe_definition', review['definition_digest'], definition)
        for value in review['requests']:
            prepared_request = ConformanceProbeRequest.model_validate(value)
            repo.put('conformance_request', prepared_request.plan_id, prepared_request)
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        for role, value in zip(('outside_mcp',), review['requests'], strict=True):
            request = ConformanceProbeRequest.model_validate(value)
            repo.authorize(request)
            assert content_digest(review['definition']) == request.mapping_digest
            repo.put('linux_task_probe_definition', request.mapping_digest, definition)
            assert repo.get('linux_task_probe_definition', request.mapping_digest) == review['definition']
            verify_dependencies(request.executable_dependencies)
            spec = ExecutorSpec.model_validate(review['definition']['profiles'][role])
            worker = binding_from_config(spec.managed_host_config().managed_worker)
            assert worker and worker.digest() == request.worker_digest
            assert worker.credential_volume is None and worker.network_id is None and worker.model_proxy_url is None
            from aeep.assessment.destinations import require_destination
            from aeep.assessment.models import AssessmentEnvironment
            require_destination(spec, AssessmentEnvironment.model_validate(repo.get('environment', request.environment_digest)), repo.authorize(request))
            canonical_setup=repo.get('linux_diagnostic_image_observation',review['setup_canonical_record_digest'])['facts']
            assert canonical_setup['setup_complete'] and canonical_setup['inspection_cleanup_confirmed']
            assert canonical_setup['image']==worker.image and canonical_setup['public_file_sha256']==review['protected_file_sha256']
            operation = 'linux-dynamic-tools-ack-managed:' + request.plan_id
            repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=60), stage='worker_inspection')
            started = time.monotonic()
            adapter = None
            facts = {'request_id': request.plan_id, 'operation_id': operation, 'image': worker.image,
                'worker_digest': worker.digest(), 'cleanup_confirmed': False, 'protocol_passed': False,
                'cpu_seconds': None, 'peak_memory_mb': None, 'accounting_complete': False}
            stage = 'adapter_initialization'
            try:
                async with asyncio.timeout(30):
                    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=router.store.host_principal_key())
                    repo.authorize(request)
                    stage = 'transport_initialize'
                    await adapter.transport.start()
                    stage = 'config_read'
                    config = await adapter.transport.request('config/read', {'includeLayers': True, 'cwd': '/workspace'})
                    snapshot = config_snapshot(config, review['expected_permissions'])
                    facts.update(snapshot)
                    del config
                    stage = 'effective_requirements'
                    requirements = (await adapter.transport.request('configRequirements/read', {})).get('requirements')
                    assert isinstance(requirements, dict), 'managed requirements unavailable'
                    assert all(requirements.get(k) == v for k, v in review['effective_requirements_expected'].items()), 'managed requirements differ'
                    facts['managed_requirements_match'] = True
                    stage = 'dynamic_declaration_ack'
                    params = review['thread_start_params']
                    assert 'dynamicTools' in params and params['ephemeral'] is True
                    response = await adapter.transport.request('thread/start', params)
                    active = response.get('activePermissionProfile')
                    assert isinstance(active, dict) and active.get('id') == 'aeep' and active.get('extends') is None
                    assert response.get('cwd') == '/workspace' and response.get('approvalPolicy') == 'never'
                    facts['dynamic_declaration_request_accepted'] = True
                    facts['thread_identity_sha256'] = hashlib.sha256(response['thread']['id'].encode()).hexdigest()
                    facts['declaration_sha256'] = review['declaration_sha256']
                    facts['permission_profile_ack'] = {'id': active['id'], 'extends': active.get('extends')}
                    facts['runtime_version'] = adapter.transport.protocol_version
                    assert '0.159.2' in adapter.transport.protocol_version, 'runtime version differs'
                    facts['configuration_initialization_passed']=True
                    facts['protocol_passed']=True
            except Exception as exc:
                facts['safe_transport'] = safe_transport_facts(adapter, exc)
                import traceback
                facts['safe_stack'] = [{'module': Path(frame.filename).name, 'function': frame.name, 'line': frame.lineno} for frame in traceback.extract_tb(exc.__traceback__)[-6:]]
                facts['error_type'] = type(exc).__name__
                facts['failing_stage'] = stage
                facts['error_class'] = ('timeout' if isinstance(exc, TimeoutError) else 'protocol_or_configuration' if type(exc).__name__ in {'CodexProtocolError', 'ConfigurationError'} else 'assertion_failed' if isinstance(exc, AssertionError) else 'unclassified')
            finally:
                if adapter is not None:
                    facts.setdefault('safe_transport', safe_transport_facts(adapter))
                    try:
                        await asyncio.wait_for(adapter.transport.close(), 3)
                    except Exception as exc:
                        facts['transport_cleanup_error_type'] = type(exc).__name__
                    try:
                        facts['cleanup_confirmed'] = bool(adapter._worker_process_id) and await asyncio.wait_for(worker.cleanup(adapter._worker_process_id or ''), 8)
                    except Exception as exc:
                        facts['cleanup_error_type'] = type(exc).__name__
                    if adapter._worker_security:
                        try:
                            adapter._worker_security.cleanup()
                        except OSError as exc:
                            facts['security_cleanup_error_type'] = type(exc).__name__
                facts['elapsed_seconds'] = time.monotonic() - started
                repo.finish_operation(operation, elapsed_seconds=facts['elapsed_seconds'], accounting=None, resources=None)
                document = Result(facts=facts)
                facts['canonical_record_digest'] = repo.put('linux_task_boundary_observation', content_digest(document), document)
                result['workers'][role] = facts
            if not facts['protocol_passed'] or not facts['cleanup_confirmed']:
                break
        result['configuration_initialization_passed'] = len(result['workers']) == 1 and all(f['protocol_passed'] and f['cleanup_confirmed'] for f in result['workers'].values())
    finally:
        result['classification'] = ('linux_dynamic_declaration_request_accepted' if result.get('configuration_initialization_passed') else 'linux_dynamic_declaration_ack_failed')
        result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        row = router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone()
        result['grant_after'] = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), row))
        if not result['source_unchanged']:
            result['configuration_initialization_passed'] = False
            result['classification'] = 'source_drift'
        result['accounting_delta'] = {key: str(Decimal(result['grant_after'][key]) - Decimal(result['grant_before'][key])) if key == 'cash_usd' else result['grant_after'][key] - result['grant_before'][key] for key in result['grant_before']}
        (OUT / 'linux-dynamic-tools-ack-managed-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        await router.close()


asyncio.run(main())
