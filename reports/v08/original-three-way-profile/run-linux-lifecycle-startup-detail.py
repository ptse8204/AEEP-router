"""Inert until exact review hash supplied; supplementary inspection, never a model trial."""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_pair_inspection import command
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, StrictModel
from aeep.router import Router


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
        classes = (('unsupported_flag', ('unexpected argument', 'unrecognized option', 'unknown option')), ('permission_denied', ('permission denied', 'operation not permitted')), ('missing_path', ('no such file or directory', 'does not exist')), ('invalid_permission_profile', ('invalid permission', 'invalid filesystem', 'permission profile')), ('invalid_configuration', ('error loading configuration', 'failed to load config', 'invalid configuration')), ('namespace_unavailable', ('namespace', 'unshare')), ('seccomp_unavailable', ('seccomp',)), ('landlock_unavailable', ('landlock',)), ('bwrap_mentioned', ('bwrap', 'bubblewrap')))
        facts['config_error_categories']=[name for name,marker in [('untagged_enum_mismatch','did not match any variant of untagged enum'),('invalid_type','invalid type'),('invalid_value','invalid value'),('missing_field','missing field'),('unknown_field','unknown field'),('toml_parse','toml parse error'),('override_parse','error parsing'),('requirements_rejection','disallowed by requirements')] if marker in text]
        fields=('permissions','aeep','filesystem','mcp_servers','linux_boundary_diagnostic','command','args','identity','executable','value','match')
        facts['recognized_public_config_fields']=[field for field in fields if re.search(r'(?<![a-z_])'+re.escape(field)+r'(?![a-z_])',text)]
        facts['recognized_error_types']=[kind for kind in ('map','string','sequence','integer','boolean','enum','struct','table') if re.search(r'\b'+kind+r'\b',text)]
        enum_match=re.search(r'untagged enum ([A-Za-z_][A-Za-z0-9_]*)',data.decode('utf-8',errors='replace'))
        known_enums={'FilesystemPermissionEntryToml','PermissionsFilesystemEntryToml','McpServerIdentity','RawMcpServerIdentity','RawMcpServerConfig','McpServerRequirement','PermissionProfileToml','FeatureToml','PluginConfigToml'}
        if enum_match and enum_match.group(1) in known_enums:facts['known_config_enum']=enum_match.group(1)
        facts['stderr_class'] = next((name for name, markers in classes if any(marker in text for marker in markers)), 'unclassified' if data else 'none')
        auth_related=re.search(r'\b(auth|authentication|authorization|login|sign.?in|token|credential|bearer|password|secret|cookie|oauth|session)\b',text)
        config_related=any(marker in text for marker in ('configuration','config','toml','deserialize','invalid type','untagged enum','permissions','mcp','error parsing','unexpected argument','unrecognized option','mcp startup','handshaking','connection closed','spawn','bwrap','namespace','permission denied','no such file','initialize response'))
        if auth_related:
            facts['error_excerpt_withheld']='authentication_related_output'
        elif config_related:
            excerpt=data.decode('utf-8',errors='replace')
            excerpt=re.sub(r'https?://[^\s\"\']+', '[redacted-url]', excerpt)
            known_paths={'/workspace/private-state.json','/opt/aeep/linux-mcp-server.py','/etc/codex/requirements.toml','/opt/aeep/worker-config.json','/opt/codex/codex','/workspace'}
            excerpt=re.sub(r'/[^\s\"\',;:)]+',lambda m:m.group(0) if m.group(0) in known_paths else '[redacted-path]',excerpt)
            excerpt=re.sub(r'[A-Za-z0-9_-]{32,}', '[redacted-long-value]',excerpt)
            facts['sanitized_config_error_excerpt']=excerpt.encode('utf-8')[:2048].decode('utf-8',errors='ignore')
        else:
            facts['error_excerpt_withheld']='not_identified_as_configuration_text'
        facts['stderr_bytes_retained'] = len(data)
        facts['stderr_truncated'] = transport.stderr_truncated
    return facts


def sanitize_error_excerpt(message):
    from types import SimpleNamespace
    carrier=SimpleNamespace(transport=SimpleNamespace(_process=None,stderr=message.encode('utf-8')[:65536],stderr_truncated=len(message.encode('utf-8'))>65536))
    result=safe_transport_facts(carrier)
    return {key:value for key,value in result.items() if key in {'sanitized_config_error_excerpt','error_excerpt_withheld','config_error_categories','recognized_public_config_fields','recognized_error_types','stderr_bytes_retained','stderr_truncated'}}


async def main():
    path = OUT / 'linux-lifecycle-startup-detail-review.json'
    assert len(sys.argv) == 2 and hashlib.sha256(path.read_bytes()).hexdigest() == sys.argv[1]
    review = json.loads(path.read_text())
    assert review['execution_authorized'] is True
    assert verification_source_digest(ROOT) == review['source_digest']
    assert not (OUT / 'linux-lifecycle-startup-detail-result.json').exists()
    router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
    repo = service.repository
    result = {'source_digest': review['source_digest'], 'model_turns': 0, 'full_conformance': False, 'workers': {}}
    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        for role, value in zip(('outside_mcp',), review['requests'], strict=True):
            request = ConformanceProbeRequest.model_validate(value)
            repo.authorize(request)
            assert content_digest(review['definition']) == request.mapping_digest
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
            operation = 'linux-lifecycle-startup-detail:' + request.plan_id
            repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=60), stage='worker_inspection')
            started = time.monotonic()
            adapter = None
            facts = {'request_id': request.plan_id, 'operation_id': operation, 'image': worker.image,
                'worker_digest': worker.digest(), 'cleanup_confirmed': False, 'protocol_passed': False,
                'cpu_seconds': None, 'peak_memory_mb': None, 'accounting_complete': False}
            stage = 'adapter_initialization'
            try:
                async with asyncio.timeout(40):
                    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=router.store.host_principal_key())
                    repo.authorize(request)
                    stage = 'transport_initialize'
                    await adapter.transport.start()
                    from aeep.hosts.codex_invocation import advertised_tools, contract_digest
                    stage = 'effective_requirements'
                    requirements=(await adapter.transport.request('configRequirements/read', {})).get('requirements')
                    assert isinstance(requirements,dict)
                    facts['observed_allowed_profiles']={k:v for k,v in requirements.get('allowedPermissionProfiles',{}).items() if k in {'aeep','aeep-task-child'} and type(v) is bool}
                    assert all(requirements.get(k)==v for k,v in review['effective_requirements_expected'].items())
                    facts['effective_requirements_matches']=True
                    stage = 'thread_start'
                    thread = await adapter.transport.request('thread/start', {'ephemeral': True, 'model': 'gpt-6.1-sol', 'cwd': '/workspace', 'permissions': 'aeep', 'approvalPolicy': 'never', 'approvalsReviewer': 'user'})
                    assert thread.get('activePermissionProfile', {}).get('id') == 'aeep'
                    assert thread.get('approvalPolicy') == 'never'
                    thread_id = thread['thread']['id']
                    stage='own_server_status'
                    await asyncio.sleep(1)
                    payload=await adapter.transport.request('mcpServerStatus/list',{'threadId':thread_id,'detail':'toolsAndAuthOnly','limit':100},timeout=5)
                    own=next((x for x in payload.get('data',[]) if x.get('name')=='linux_boundary_diagnostic'),None)
                    facts['own_server_present']=own is not None
                    if own and isinstance(own.get('toolsError'),str):facts['own_server_error']=sanitize_error_excerpt(own['toolsError'])
                    stage='fixed_server_startup_exception'
                    name='aeep-'+hashlib.sha256((adapter._worker_process_id or '').encode()).hexdigest()[:32]
                    argv=[worker.runtime,'--host','unix://'+worker.socket,'exec','--user','65534:65534',name,'/usr/local/bin/python3','-I','-c',review['definition']['programs']['startup_detail']]
                    facts['diagnostic_argv']=argv
                    proc=await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
                    try:output,_=await asyncio.wait_for(proc.communicate(),8)
                    finally:
                        if proc.returncode is None:proc.kill();await asyncio.wait_for(proc.wait(),1)
                    assert proc.returncode==0 and len(output)<4096
                    facts['fixed_server_startup']=json.loads(output)
                    facts['protocol_passed']=True
            except Exception as exc:
                facts['safe_transport'] = safe_transport_facts(adapter, exc)
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
        result['probe_supported'] = len(result['workers']) == 1 and all(f['protocol_passed'] and f['cleanup_confirmed'] for f in result['workers'].values())
    finally:
        result['classification'] = ('own_server_startup_diagnostic_completed' if result.get('probe_supported') else 'own_server_startup_diagnostic_failed')
        result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        row = router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone()
        result['grant_after'] = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), row))
        (OUT / 'linux-lifecycle-startup-detail-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        await router.close()


asyncio.run(main())
