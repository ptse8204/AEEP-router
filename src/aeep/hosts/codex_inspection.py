"""Reviewed, turn-free worker inspection. Protocol details stay in this adapter module."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal
from urllib.parse import urlsplit

from ..assessment.boundary import BoundaryProbeDefinition
from ..assessment.identity import runtime_dependencies, verify_dependencies
from ..assessment.models import (
    AssessmentLimits,
    ConformanceProbeRequest,
    Digest,
    RecipeRuntimeBinding,
    content_digest,
)
from ..assessment.service import AssessmentService
from ..errors import ConfigurationError
from ..execution import EventJournal, ExecutionEvidence, persist_execution_events, start_execution
from ..models import ExecutionStatus, RawExecution, StrictModel
from .codex_app_server import CodexAppServerAdapter, CodexRequestError
from .workers import binding_from_config

# Fixed program, synthetic files only. No credential names or contents are read.
# Missing paths are distinct from permission denial; neither proves isolation alone.
COMMAND = '''import errno,json,pathlib,socket
result={}
p=pathlib.Path('/workspace/aeep-inspection.txt')
try:
 with p.open('x') as f:f.write('synthetic')
 result['workspace_write']=p.read_text()=='synthetic';p.unlink()
except OSError:result['workspace_write']=False
try:
 p=pathlib.Path('/opt/aeep/.inspection-write')
 with p.open('x') as f:f.write('synthetic')
 p.unlink();result['configuration_write']='permitted'
except PermissionError:result['configuration_write']='denied'
except FileNotFoundError:result['configuration_write']='absent'
except OSError as exc:result['configuration_write']='read_only' if exc.errno==errno.EROFS else 'unavailable'
for name,endpoint in [('proxy',(PROXY_HOST,PROXY_PORT)),('direct',('1.1.1.1',443))]:
 sock=None
 try:
  sock=socket.socket();sock.settimeout(1);sock.connect(endpoint);result[name]='permitted'
 except PermissionError:result[name]='denied'
 except OSError:result[name]='unreachable'
 finally:
  if sock is not None:sock.close()
print(json.dumps(result))
'''


def prepare(service: AssessmentService, source_request_id: str) -> ConformanceProbeRequest:
    """Create an inert exact definition; preparing it grants no authority."""
    repo = service.repository
    source = ConformanceProbeRequest.model_validate(repo.get('conformance_request', source_request_id))
    definition = BoundaryProbeDefinition.model_validate(repo.get('boundary_probe_definition', source.mapping_digest))
    config = definition.executor.managed_host_config()
    worker = binding_from_config(config.managed_worker)
    if worker is None or config.adapter_id.split(':', 1)[0] != 'codex-app-server':
        raise ConfigurationError('inspection requires a reviewed Codex App Server worker')
    mapping = BoundaryProbeDefinition(name='worker_inspection', executor=definition.executor, expected={})
    mapping_digest = repo.put('boundary_probe_definition', content_digest(mapping), mapping)
    dependencies = runtime_dependencies()
    runtime = RecipeRuntimeBinding(dependencies=dependencies)
    runtime_digest = repo.put('probe_runtime', content_digest(runtime), runtime)
    request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',
        operation='worker_inspection', subject_digest=source.subject_digest, recipe_digest=source.recipe_digest,
        environment_digest=source.environment_digest, authorization_id=source.authorization_id,
        mapping_digest=mapping_digest, definition_digests=[mapping_digest, runtime_digest, source.recipe_digest,
                                                        source.environment_digest],
        worker_digest=worker.digest(), executable_dependencies=dependencies)
    repo.put('conformance_request', request.plan_id, request)
    return request


def policy_observations(payload: dict[str, Any], expectations: dict[str, Any]) -> dict[str, Any]:
    """Compare only reviewed fields; never retain raw configuration or unknown values."""
    result = {}
    for path, expected in expectations.items():
        current: Any = payload
        for component in path.split('/'):
            current = current.get(component) if isinstance(current, dict) else None
        result[path] = {'present': current is not None,
                        'matches': content_digest({'value': current}) == content_digest({'value': expected}),
                        'expected': expected}
    return result


def summarized_inventory(catalog: dict[str, Any]) -> dict[str, Any]:
    """Retain declarations only. Catalog presence never proves permission."""
    return {
        'skills': [{key: value.get(key) for key in ('name', 'path', 'enabled')} for value in catalog['skills']],
        'apps': [{key: value.get(key) for key in ('id', 'enabled', 'callable')} for value in catalog['apps']],
        'servers': [{'name': value.get('name'), 'tool_names': sorted(value['tools']),
                     'complete': not bool(value.get('toolsError'))} for value in catalog['servers']],
    }


async def collect(adapter: CodexAppServerAdapter, config: Any, journal: EventJournal,
                  recheck: Any) -> dict[str, Any]:
    """Inspect supported reads and one fixed sandbox command; never call turn/start."""
    observations: dict[str, Any] = {'full_conformance': False, 'model_turns': 0}
    stage = 'identity'
    try:
        recheck()
        observations['identity_digest'] = await adapter.resolve_identity(config)
        observations['protocol_version'] = adapter.transport.protocol_version
        models = await adapter.list_models()
        observations['models'] = [{'id': m.id, 'reasoning_efforts': list(m.reasoning_efforts)} for m in models]
        for method, params, expected in (
            ('config/read', {'includeLayers': False, 'cwd': '/workspace'}, {
                'config/default_permissions': 'aeep', 'config/approval_policy': 'never',
                'config/web_search': 'disabled', 'config/mcp_servers': {}, **{f'config/features/{key}': False for key in
                    ('apps', 'memories', 'multi_agent', 'browser_use', 'computer_use')}}),
            ('configRequirements/read', {}, {'requirements/allowedPermissionProfiles': {'aeep': True},
                'requirements/allowedApprovalPolicies': ['never'],
                'requirements/allowedWebSearchModes': ['disabled']}),
        ):
            stage = method
            recheck()
            journal.append('action.started', method+'-start')
            try:
                payload = await adapter.transport.request(method, params)
                observations[method] = policy_observations(payload, expected)
                journal.append('action.completed', method+'-complete')
            except CodexRequestError:
                observations[method] = {'available': False}
                journal.append('action.completed', method+'-unavailable')
        stage = 'inventory'
        recheck()
        policy = observations['config/read']
        if all(policy.get(key, {}).get('matches') is True for key in
               ('config/mcp_servers', 'config/features/apps')):
            observations['advertised_inventory'] = summarized_inventory(await adapter.inventory())
        else:
            # Inventory can initialize MCP processes. Do not start unknown ones.
            observations['advertised_inventory'] = {'available': False,
                'reason': 'empty MCP configuration and disabled apps are not verified'}
        stage = 'sandbox_command'
        worker = binding_from_config(config.managed_worker)
        if worker is None or worker.model_proxy_url is None:
            raise ConfigurationError('inspection requires its reviewed proxy endpoint')
        proxy = urlsplit(worker.model_proxy_url)
        command = COMMAND.replace('PROXY_HOST', repr(proxy.hostname)).replace('PROXY_PORT', repr(proxy.port))
        recheck()
        journal.append('action.started', 'sandbox-command-start', action_digest=content_digest({"program": command}))
        response = await adapter.transport.request('command/exec', {
            'command': ['python3', '-c', command], 'cwd': '/workspace',
            'timeoutMs': 10000, 'outputBytesCap': 4096,
        }, timeout=15)
        # No policy override: observe the actual configured managed default.
        output = response.get('stdout')
        if response.get('exitCode') != 0 or not isinstance(output, str) or len(output.encode()) > 4096:
            raise ConfigurationError('sandbox command did not return a bounded observation')
        parsed = json.loads(output)
        expected_keys = {'workspace_write', 'configuration_write', 'proxy', 'direct'}
        if (not isinstance(parsed, dict) or set(parsed) != expected_keys
                or type(parsed['workspace_write']) is not bool
                or parsed['configuration_write'] not in {'permitted', 'denied', 'read_only', 'absent', 'unavailable'}
                or any(parsed[key] not in {'permitted', 'denied', 'unreachable'}
                       for key in ('proxy', 'direct'))):
            raise ConfigurationError('sandbox command observation is malformed')
        observations['sandbox_command'] = parsed
        journal.append('action.completed', 'sandbox-command-complete')
        recheck()
        observations['inspection_complete'] = True
    except Exception as exc:
        observations.update(inspection_complete=False, failed_stage=stage, error_type=type(exc).__name__)
    return observations


class WorkerInspectionResult(StrictModel):
    schema_version: Literal['assessment.worker-inspection.v1'] = 'assessment.worker-inspection.v1'
    request_id: str
    worker_digest: Digest
    execution_evidence_digest: Digest | None
    observations: dict[str, Any]


async def execute(service: AssessmentService, request_id: str) -> WorkerInspectionResult:
    repo = service.repository
    request = ConformanceProbeRequest.model_validate(repo.get('conformance_request', request_id))
    if request.operation != 'worker_inspection':
        raise ConfigurationError('worker inspection requires its own reviewed request')
    repo.authorize(request)
    verify_dependencies(request.executable_dependencies)
    definition = BoundaryProbeDefinition.model_validate(repo.get('boundary_probe_definition', request.mapping_digest))
    config = definition.executor.managed_host_config()
    worker = binding_from_config(config.managed_worker)
    if (definition.name != 'worker_inspection' or content_digest(definition) != request.mapping_digest
            or worker is None or worker.digest() != request.worker_digest
            or config.adapter_id.split(':', 1)[0] != 'codex-app-server'):
        raise ConfigurationError('worker inspection differs from its reviewed definition')
    from ..assessment.destinations import require_destination
    from ..assessment.models import AssessmentEnvironment
    require_destination(definition.executor, AssessmentEnvironment.model_validate(
        repo.get('environment', request.environment_digest)), repo.authorize(request))
    operation = 'inspection:'+request.plan_id
    repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=120), stage='worker_inspection')
    started = time.perf_counter()
    facts: dict[str, Any] = {'inspection_complete': False, 'full_conformance': False, 'model_turns': 0}
    evidence_digest = None

    async def invoke(journal: EventJournal) -> RawExecution:
        adapter = None
        try:
            adapter = CodexAppServerAdapter.from_executor(definition.executor,
                principal_salt=service.router.store.host_principal_key())
            async with asyncio.timeout(90):
                facts.update(await collect(adapter, config, journal, lambda: repo.authorize(request)))
        except Exception as exc:
            facts.update(inspection_complete=False, error_type=type(exc).__name__)
        finally:
            cleaned = False
            try:
                if adapter is not None:
                    try:
                        await asyncio.wait_for(adapter.transport.close(), timeout=5)
                    finally:
                        if adapter._worker_process_id:
                            cleaned = await asyncio.wait_for(worker.cleanup(adapter._worker_process_id), timeout=20)
            except Exception as exc:
                facts['inspection_complete'] = False
                facts['cleanup_error_type'] = type(exc).__name__
            finally:
                if adapter is not None and adapter._worker_security:
                    adapter._worker_security.cleanup()
                facts['cleanup_confirmed'] = cleaned
                if not cleaned:
                    facts['inspection_complete'] = False
        journal.append('artifact.created', 'inspection-observations', evidence_ref=content_digest(facts))
        return RawExecution(status=ExecutionStatus.SUCCESS if facts['inspection_complete'] else ExecutionStatus.FAILED,
            output=dict(facts), metadata={'boundary_digest': worker.digest(),
                                         'host_runtime_digest': facts.get('identity_digest')})

    try:
        with persist_execution_events(lambda journal_id, event: repo.put(
                'execution_event', journal_id+':'+str(event.sequence), event)):
            handle = start_execution(operation, config.adapter_id, invoke)
            raw = await handle.task
        evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
        evidence_digest = repo.put('execution_evidence', evidence.digest(), evidence)
    finally:
        repo.finish_operation(operation, elapsed_seconds=time.perf_counter()-started)
        result = WorkerInspectionResult(request_id=request.plan_id, worker_digest=worker.digest(),
            execution_evidence_digest=evidence_digest, observations=facts)
        repo.put('worker_inspection', operation, result)
    return result
