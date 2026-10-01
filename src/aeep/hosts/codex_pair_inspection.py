"""Reviewed paired Codex worker observations; no model turns or implicit conformance."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import model_validator

from ..assessment.boundary import BoundaryProbe, BoundaryProbeDefinition
from ..assessment.destinations import require_destination
from ..assessment.identity import runtime_dependencies, verify_dependencies
from ..assessment.models import (
    AssessmentEnvironment,
    AssessmentLimits,
    ConformanceProbeRequest,
    DifferentialEnvironment,
    Digest,
    RecipeRuntimeBinding,
    content_digest,
)
from ..assessment.service import AssessmentService
from ..errors import ConfigurationError
from ..execution import EventJournal, persist_execution_events
from ..executors.base import ExecutionContext
from ..executors.command import CommandExecutor
from ..models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    RawExecution,
    StrictModel,
    new_id,
)
from .codex_app_server import CodexAppServerAdapter, CodexProtocolError
from .codex_inspection import collect
from .workers import ManagedWorkerBinding, binding_from_config, validate_worker_pair

# All paths are synthetic canaries or reviewed public dependencies. No auth files.
CHECK = '''import hashlib,io,json,pathlib
import pandas,openpyxl
p=pathlib.Path
result={}
for label,name in PATHS.items():
 try:result[label]='readable' if p(name).read_bytes() else 'empty'
 except PermissionError:result[label]='denied'
 except FileNotFoundError:result[label]='absent'
 except IsADirectoryError:result[label]='directory'
buf=io.BytesIO();pandas.DataFrame({'value':[3,7]}).to_excel(buf,index=False)
book=openpyxl.load_workbook(io.BytesIO(buf.getvalue()))
result['shared_workbook_roundtrip']=book.active['A3'].value==7
result['pandas']=pandas.__version__;result['openpyxl']=openpyxl.__version__
skill=p('/opt/dependencies/plugin/skills/spreadsheets/SKILL.md')
if skill.is_symlink() or any(parent.is_symlink() for parent in skill.parents):raise ValueError('unsafe candidate path')
result['candidate_skill_sha256']=hashlib.sha256(skill.read_bytes()).hexdigest() if skill.is_file() else None
alias=p('/etc/codex/skills/spreadsheets/SKILL.md')
if alias.is_file() and alias.resolve()!=skill.resolve():raise ValueError('unexpected candidate alias')
result['candidate_alias']=alias.is_file()
result['candidate_runtime']=p('/opt/dependencies/runtime').is_dir()
print(json.dumps(result))
'''
SEED = '''import json,os,pathlib,re,sys
p=json.load(sys.stdin)
if not re.fullmatch('aeep-synthetic-[a-f0-9]{32}',p['name']):raise ValueError('invalid canary')
root=os.open('/worker/auth',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
 fd=os.open(p['name'],os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=root)
 with os.fdopen(fd,'w') as f:f.write('synthetic-only')
finally:os.close(root)
cgroup=pathlib.Path('/sys/fs/cgroup')
print(json.dumps({name:(cgroup/name).read_text().strip() for name in ['cpu.max','memory.max','pids.max']}))
'''

REMOVE_CANARY = '''import json,os,re,sys
p=json.load(sys.stdin)
if not re.fullmatch('aeep-synthetic-[a-f0-9]{32}',p['name']):raise ValueError('invalid canary')
root=os.open('/worker/auth',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
 try:os.unlink(p['name'],dir_fd=root)
 except FileNotFoundError:pass
finally:os.close(root)
print('{}')
'''

DEPENDENCY = r'''import json,pathlib,subprocess
root=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
node=root/'node/bin/node'
pathlib.Path('/workspace/node_modules').symlink_to(root/'node_modules')
helper='/etc/codex/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs'
marked=subprocess.run([str(node),helper,'--operation-kind','create','--expected-output-count','1','--output-format','xlsx'],capture_output=True,timeout=10)
script="import {Workbook} from '@oai/artifact-tool';import assert from 'node:assert/strict';const w=await Workbook.fromCSV('id,name\\n1,Ada\\n',{sheetName:'Fixture'});assert.deepEqual(w.worksheets.getItem('Fixture').getRange('A1:B2').values,[['id','name'],['1','Ada']]);"
pathlib.Path('/workspace/dependency-probe.mjs').write_text(script)
ran=subprocess.run([str(node),'/workspace/dependency-probe.mjs'],capture_output=True,timeout=15)
print(json.dumps({'authoring_helper':marked.returncode==0,'artifact_tool_csv':ran.returncode==0}))
'''

# This first reviewed profile checks the installed Spreadsheets bundle, not an
# arbitrary executable supplied by plugin metadata.
CANDIDATE_PATHS = {'/opt/dependencies/plugin/skills/spreadsheets/SKILL.md',
                   '/etc/codex/skills/spreadsheets/SKILL.md', '/opt/dependencies/runtime'}
SKILL_PROFILES: dict[str, tuple[str, str, str, set[str]]] = {
    'spreadsheets:1': ('/opt/dependencies/plugin/skills/spreadsheets/SKILL.md',
                       '/etc/codex/skills/spreadsheets/SKILL.md', '/opt/dependencies/runtime',
                       {'Spreadsheets', 'spreadsheets:Spreadsheets'}),
    'ponytail:1': ('/opt/dependencies/ponytail/SKILL.md',
                  '/etc/codex/skills/ponytail/SKILL.md', '/opt/dependencies/ponytail',
                  {'ponytail', 'ponytail:ponytail'}),
}


class WorkerPairInspection(StrictModel):
    schema_version: Literal['assessment.worker-pair-inspection.v1', 'assessment.worker-pair-inspection.v2', 'assessment.worker-pair-inspection.v3'] = 'assessment.worker-pair-inspection.v1'
    profile: Literal['spreadsheets:1', 'ponytail:1'] = 'spreadsheets:1'
    control: ExecutorSpec
    treatment: ExecutorSpec
    # The differential definition remains separately reviewed; paths cannot be
    # replaced with a prompt saying that the candidate is unavailable.
    differential: DifferentialEnvironment
    shared_versions: dict[str, str]
    candidate_skill_digest: Digest

    @model_validator(mode='after')
    def reviewed_pair(self) -> WorkerPairInspection:
        differential = self.differential
        skill_path, alias_path, directory, names = SKILL_PROFILES[self.profile]
        extended = self.schema_version.endswith('.v3')
        if ((not extended and self.profile != 'spreadsheets:1')
                or set(differential.candidate_paths) != {skill_path, alias_path, directory}
                or not set(differential.candidate_aliases).issubset(names)
                or (extended and not differential.candidate_aliases)
                or set(self.shared_versions) != {'pandas','openpyxl'}):
            raise ValueError('paired probe requires its exact reviewed skill profile')
        workers = []
        for spec in (self.control,self.treatment):
            config = spec.managed_host_config()
            worker = binding_from_config(config.managed_worker)
            if (worker is None or config.adapter_id.split(':',1)[0] != 'codex-app-server'
                    or config.argv != (worker.binary,'app-server') or worker.permissions_profile != 'aeep'
                    or not worker.model_proxy_url or not worker.credential_volume
                    or (not extended and config.input_tree is not None)
                    or config.store_prompt or config.store_output
                    or (config.invocation is not None and config.invocation.dynamic_tools_digest is not None)
                    or (self.schema_version.endswith('.v1') and (config.artifact is not None
                        or (config.invocation is not None and config.invocation.mode != 'turn')))):
                raise ValueError('paired probe requires protected signed-in workers with exact entrypoints')
            workers.append(worker)
        if not self.schema_version.endswith('.v1'):
            configs = [spec.managed_host_config() for spec in (self.control,self.treatment)]
            for role, config in zip(('control','treatment'),configs,strict=True):
                target = config.invocation
                if (target is None or target.local_profile != 'capable_local'
                        or (not extended and (target.native_catalog or target.supporting_skills))
                        or target.supporting_tools
                        or target.mode != ('turn' if role == 'control' else 'skill')
                        or (role == 'treatment' and (target.skill_path not in {skill_path, alias_path}
                            or target.skill_name not in differential.candidate_aliases
                            or target.skill_sha256 != self.candidate_skill_digest))):
                    raise ValueError('task-profile inspection requires the exact capable shared profile and candidate skill')
            shared = [config.model_dump(exclude={'adapter_id','managed_worker','invocation'}) for config in configs]
            if shared[0] != shared[1]:
                raise ValueError('task-profile inspection requires equivalent shared executor settings')
            targets = [config.invocation for config in configs]
            assert targets[0] is not None and targets[1] is not None
            if (targets[0].native_catalog != targets[1].native_catalog
                    or targets[0].supporting_skills != targets[1].supporting_skills):
                raise ValueError('shared native catalog must be identical in both arms')
            for background in targets[0].supporting_skills:
                if (background.name in names or background.path in differential.candidate_paths
                        or differential.control_inventory.get('skill:' + background.name) != background.sha256
                        or any((worker.reviewed_files or {}).get(background.path) != background.sha256 for worker in workers)):
                    raise ValueError('background skill must be shared, pinned and separate from the candidate')
        validate_worker_pair(*workers)
        if (workers[1].reviewed_files or {}).get(skill_path) != self.candidate_skill_digest:
            raise ValueError('candidate skill is not pinned in the treatment image')
        return self


def expected_probes(definition: WorkerPairInspection, role: str) -> dict[str, dict[str, str | bool | int]]:
    return {
        'allowed_tool': {'workspace_write':True,'dependencies':True},
        'denied_tool': {'credential_read_denied':True},
        'cross_worker': {'own_readable':True,'other_absent':True},
        'answers': {'external_answer_blocked':True},
        'configuration': {'immutable_image':True,'active_policy':True,'requirements':True,'disabled_features':True},
        'candidate_network': {'proxy_denied':True,'direct_denied':True},
        'credential_canary': {'seeded':True,'denied':True,'removed':True},
        'resource_limits': {'cpu':True,'memory':True,'processes':True,'mounts':True},
        'cleanup': {'worker_removed':True,'command_stopped':True},
        'events': {'command_responses_complete':True},
        'candidate_access': {'definition_digest':content_digest(definition.differential),'candidate_available':role == 'treatment'},
    }


def prepare_pair(service: AssessmentService, control_source: str, treatment_source: str,
                 definition: WorkerPairInspection) -> dict[str, Any]:
    repo = service.repository
    pair_digest = repo.put('worker_pair_definition',content_digest(definition),definition)
    dependencies = runtime_dependencies()
    runtime = RecipeRuntimeBinding(dependencies=dependencies)
    runtime_digest = repo.put('probe_runtime',content_digest(runtime),runtime)
    requests = []
    for role, source_id in [('control',control_source),('treatment',treatment_source)]:
        source = ConformanceProbeRequest.model_validate(repo.get('conformance_request',source_id))
        spec = getattr(definition,role)
        worker = binding_from_config(spec.managed_host_config().managed_worker)
        assert worker is not None
        original = BoundaryProbeDefinition.model_validate(repo.get('boundary_probe_definition',source.mapping_digest))
        if original.executor != spec or source.worker_digest != worker.digest():
            raise ConfigurationError('paired inspection must preserve each selected source worker')
        probe_digests = []
        for name, expected in expected_probes(definition,role).items():
            probe = BoundaryProbeDefinition(name=name,executor=spec,expected=expected)
            probe_digests.append(repo.put('boundary_probe_definition',content_digest(probe),probe))
        mapping = BoundaryProbeDefinition(name='worker_pair_inspection',executor=spec,expected={})
        mapping_digest = repo.put('boundary_probe_definition',content_digest(mapping),mapping)
        request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v3',operation='worker_pair_inspection',
            subject_digest=source.subject_digest,recipe_digest=source.recipe_digest,environment_digest=source.environment_digest,
            authorization_id=source.authorization_id,mapping_digest=mapping_digest,worker_digest=worker.digest(),
            pair_definition_digest=pair_digest,executable_dependencies=dependencies,
            definition_digests=[pair_digest,mapping_digest,runtime_digest,source.recipe_digest,source.environment_digest,*probe_digests])
        repo.put('conformance_request',request.plan_id,request)
        requests.append(request)
    if requests[0].authorization_id != requests[1].authorization_id:
        raise ConfigurationError('paired inspection requires the same existing grant')
    return {'status':'review_required','pair_definition_digest':pair_digest,
            'requests':[request.model_dump(mode='json') for request in requests],
            'maximum_operations':2,'maximum_model_turns':0,'maximum_reserved_seconds':480}


async def docker(worker: ManagedWorkerBinding, *arguments: str, payload: dict[str,str] | None = None) -> str:
    spec = ExecutorSpec(id='worker-observation',capability='worker.observation',kind=ExecutorKind.COMMAND,description='Bounded worker observation',
        config={'argv':[worker.runtime,'--host','unix://'+worker.socket,*arguments], 'argv_literal':True,
                'stdin_json':payload is not None,'max_stdin_bytes':4096,'max_output_bytes':16384,
                'timeout_seconds':15,'output':{'type':'text'}})
    raw = await CommandExecutor().execute(ExecutionContext(request=ActionRequest(capability=spec.capability,input=payload or {}),
        spec=spec,estimate=spec.estimate,attempt=1))
    if raw.status != ExecutionStatus.SUCCESS or not isinstance(raw.output,str) or raw.metadata.get('stdout_truncated'):
        raise ConfigurationError('bounded Docker observation failed')
    return raw.output


async def command(adapter: CodexAppServerAdapter, program: str, *, timeout_ms: int = 10000) -> dict[str, Any]:
    response = await adapter.transport.request('command/exec', {
        'command':['python3','-c',program], 'cwd':'/workspace',
        'timeoutMs':timeout_ms,'outputBytesCap':4096},timeout=timeout_ms/1000+5)
    output = response.get('stdout')
    if response.get('exitCode') != 0 or not isinstance(output,str) or len(output.encode()) > 4096:
        raise ConfigurationError('bounded sandbox observation failed')
    result = json.loads(output)
    if not isinstance(result,dict):
        raise ConfigurationError('sandbox observation must be an object')
    return result


def observations(definition: WorkerPairInspection, role: str, worker: ManagedWorkerBinding,
                 facts: dict[str, Any]) -> dict[str, dict[str, str | bool | int]]:
    """Derive named facts from observations, never from a caller-supplied pass flag."""
    inspect = facts['inspection']
    observed = facts['filesystem']
    cgroups = facts['cgroups']
    meta = facts['container']
    quota,period = map(int,cgroups['cpu.max'].split())
    candidate = [bool(observed[key]) for key in ('candidate_skill_sha256','candidate_alias','candidate_runtime')]
    expected = role == 'treatment'
    inventory = inspect.get('advertised_inventory',{})
    skills = inventory.get('skills',[])
    enabled = [s for s in skills if s.get('enabled') is True]
    names = SKILL_PROFILES[definition.profile][3]
    target = getattr(definition, role).managed_host_config().invocation
    backgrounds = {item.name: item.path for item in target.supporting_skills} if target else {}
    shared_skills = [item for item in enabled if item.get('name') in backgrounds
                     and item.get('path') == backgrounds[item['name']]]
    candidates = [item for item in enabled if item not in shared_skills]
    correct_inventory = (not inventory.get('apps') and not inventory.get('servers') and
        len(shared_skills) == len(backgrounds) and
        (len(candidates)==1 and candidates[0].get('name') in names if expected else not candidates))
    if expected and definition.schema_version.endswith('.v3'):
        correct_inventory &= len(candidates) == 1 and candidates[0].get('path') in SKILL_PROFILES[definition.profile][:2]
    candidate_access = (all(candidate) and observed['candidate_skill_sha256']==definition.candidate_skill_digest
                        if expected else not any(candidate)) and correct_inventory
    disabled = inspect.get('config/read',{})
    requirements = inspect.get('configRequirements/read',{})
    active = facts['active_policy']
    versions = all(observed.get(name)==version for name,version in definition.shared_versions.items())
    allowed_mounts = [m for m in meta['mounts'] if m.get('Type') in {'volume','bind'}]
    mount_ok = (len(allowed_mounts)==1 and allowed_mounts[0].get('Type')=='volume'
                and allowed_mounts[0].get('Name')==worker.credential_volume and allowed_mounts[0].get('Destination')=='/worker/auth')
    return {
        'allowed_tool': {'workspace_write':inspect['sandbox_command']['workspace_write'] is True,
                         'dependencies':observed['shared_workbook_roundtrip'] is True and versions and (not expected
                             or definition.profile == 'ponytail:1'
                             or facts.get('dependencies')=={'authoring_helper':True,'artifact_tool_csv':True})},
        'denied_tool': {'credential_read_denied':observed['credential_canary']=='denied'},
        'cross_worker': {'own_readable':observed['own_workspace']=='readable','other_absent':observed['other_workspace']=='absent'},
        'answers': {'external_answer_blocked':observed['external_answer'] in {'denied','absent'}},
        'configuration': {'immutable_image':meta['readonly'] is True and meta['image']==worker.image,
            'active_policy':active=={'profile_matches':True,'approval_never':True,'cwd_matches':True},
            'requirements':all(isinstance(item,dict) and item.get('matches') is True for item in requirements.values()) and len(requirements)==3,
            'disabled_features':all(disabled.get(key,{}).get('matches') is True for key in
                ('config/web_search','config/mcp_servers',*(f'config/features/{name}' for name in ('apps','memories','multi_agent','browser_use','computer_use'))))},
        'candidate_network': {'proxy_denied':inspect['sandbox_command']['proxy']=='denied','direct_denied':inspect['sandbox_command']['direct']=='denied'},
        'credential_canary': {'seeded':facts.get('canary_seeded') is True,'denied':observed['credential_canary']=='denied','removed':facts.get('canary_removed') is True},
        'resource_limits': {'cpu':quota/period==worker.cpu_count,'memory':int(cgroups['memory.max'])==worker.memory_mb*1024*1024,
            'processes':int(cgroups['pids.max'])==worker.process_limit,'mounts':mount_ok and meta['network']==worker.network_id},
        'cleanup': {'worker_removed':facts.get('cleanup_confirmed') is True,'command_stopped':facts.get('command_stopped') is True},
        'events': {'command_responses_complete':inspect.get('inspection_complete') is True and facts.get('collection_complete') is True},
        'candidate_access': {'definition_digest':content_digest(definition.differential),
                             'candidate_available':expected if candidate_access else 'inconsistent'},
    }


def filesystem_observation(value: dict[str, Any]) -> dict[str, Any]:
    statuses = {'own_workspace','other_workspace','credential_canary','external_answer'}
    booleans = {'shared_workbook_roundtrip','candidate_alias','candidate_runtime'}
    versions = {'pandas','openpyxl'}
    if (set(value) != statuses | booleans | versions | {'candidate_skill_sha256'}
            or any(value[key] not in {'readable','empty','directory','denied','absent'} for key in statuses)
            or any(type(value[key]) is not bool for key in booleans)
            or any(not isinstance(value[key],str) or not re.fullmatch(r'[A-Za-z0-9.+_-]{1,64}',value[key]) for key in versions)
            or (value['candidate_skill_sha256'] is not None and not re.fullmatch(r'[a-f0-9]{64}',str(value['candidate_skill_sha256'])))):
        raise ConfigurationError('malformed filesystem observation')
    return value


def container_observation(value: dict[str, Any], worker: ManagedWorkerBinding) -> dict[str, Any]:
    mounts = value.get('mounts')
    if (not isinstance(mounts,list) or len(mounts)>16 or not all(isinstance(m,dict) for m in mounts)
            or type(value.get('readonly')) is not bool):
        raise ConfigurationError('malformed container observation')
    # Retain only reviewed metadata; never store environment, labels or host paths.
    return {'image':worker.image if value.get('image')==worker.image else 'unexpected',
        'readonly':value['readonly'],'network':worker.network_id if value.get('network')==worker.network_id else 'unexpected',
        'mounts':[{'Type':m.get('Type') if m.get('Type') in {'volume','bind','tmpfs'} else 'unexpected',
                   'Name':worker.credential_volume if m.get('Name')==worker.credential_volume else 'unexpected',
                   'Destination':'/worker/auth' if m.get('Destination')=='/worker/auth' else 'unexpected'} for m in mounts]}


def authorize_pair(service: AssessmentService, control_request: str, treatment_request: str) -> tuple[WorkerPairInspection, list[ConformanceProbeRequest], list[ManagedWorkerBinding], list[dict[str, BoundaryProbeDefinition]]]:
    """Validate the entire reviewed pair before admitting either operation."""
    repo = service.repository
    roles = ('control','treatment')
    requests = [ConformanceProbeRequest.model_validate(repo.get('conformance_request',identity))
                for identity in (control_request,treatment_request)]
    if (any(r.operation != 'worker_pair_inspection' for r in requests)
            or requests[0].pair_definition_digest != requests[1].pair_definition_digest
            or requests[0].authorization_id != requests[1].authorization_id):
        raise ConfigurationError('paired inspection requires two matching reviewed requests')
    definition = WorkerPairInspection.model_validate(repo.get('worker_pair_definition',requests[0].pair_definition_digest or ''))
    if content_digest(definition) != requests[0].pair_definition_digest:
        raise ConfigurationError('paired inspection definition drift')
    workers = []
    probe_definitions: list[dict[str, BoundaryProbeDefinition]] = []
    for role, request in zip(roles,requests,strict=True):
        grant = repo.authorize(request)
        verify_dependencies(request.executable_dependencies)
        if not request.executable_dependencies:
            raise ConfigurationError('paired inspection runtime identity is missing')
        spec = getattr(definition,role)
        worker = binding_from_config(spec.managed_host_config().managed_worker)
        mapping = BoundaryProbeDefinition.model_validate(repo.get('boundary_probe_definition',request.mapping_digest))
        if (worker is None or worker.digest()!=request.worker_digest or mapping.executor!=spec
                or mapping.name!='worker_pair_inspection' or content_digest(mapping)!=request.mapping_digest):
            raise ConfigurationError('paired inspection worker differs from its request')
        require_destination(spec,AssessmentEnvironment.model_validate(repo.get('environment',request.environment_digest)),grant)
        definitions = {}
        for name,expected in expected_probes(definition,role).items():
            probe = BoundaryProbeDefinition(name=name,executor=spec,expected=expected)
            if content_digest(probe) not in request.definition_digests:
                raise ConfigurationError('paired inspection probe definition is not reviewed')
            if repo.get('boundary_probe_definition',content_digest(probe)) != probe.model_dump(mode='json'):
                raise ConfigurationError('paired inspection probe definition drift')
            definitions[name] = probe
        probe_definitions.append(definitions)
        workers.append(worker)
    return definition,requests,workers,probe_definitions


async def execute_pair(service: AssessmentService, control_request: str, treatment_request: str) -> dict[str, Any]:
    """One-shot paired observations, charged to the existing grant, never admissions."""
    from .codex_app_server import _select_model_config
    from .codex_inspection import WorkerInspectionResult

    repo = service.repository
    roles = ('control','treatment')
    definition,requests,workers,probe_definitions = authorize_pair(service,control_request,treatment_request)
    operations = ['pair-inspection:'+r.plan_id for r in requests]
    reserved: list[tuple[str,float]] = []
    try:
        for request,operation in zip(requests,operations,strict=True):
            repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=240),stage='worker_pair_inspection')
            reserved.append((operation,time.perf_counter()))
    except BaseException:
        # No process has started. Preserve the admitted operation and actual
        # admission overhead if the other reservation loses a budget race.
        for operation,started in reserved:
            repo.finish_operation(operation,elapsed_seconds=time.perf_counter()-started)
        raise

    facts: list[dict[str,Any]] = [dict(full_conformance=False,model_turns=0) for _ in roles]
    adapters: list[CodexAppServerAdapter] = []
    journals: list[EventJournal] = []
    canary = 'aeep-synthetic-'+uuid4().hex
    markers = ['control-'+uuid4().hex,'treatment-'+uuid4().hex]
    pending: asyncio.Task[dict[str,Any]] | None = None
    failure: BaseException | None = None
    stage = 'start'
    result: dict[str, Any] = {'pair_definition_digest':content_digest(definition), 'model_turns':0,
                             'full_conformance':False,'workers':{}}

    def recheck() -> None:
        for request in requests:
            repo.authorize(request)

    async def observed_command(index: int, name: str, program: str, timeout_ms: int = 10000) -> dict[str, Any]:
        recheck()
        journal = journals[index]
        journal.append('action.started',name+'-start',action_digest=content_digest({'program':program}))
        output = await command(adapters[index],program,timeout_ms=timeout_ms)
        journal.append('action.completed',name+'-complete')
        return output

    async def remove_canary(index: int) -> None:
        worker,adapter = workers[index],adapters[index]
        if facts[index].get('canary_attempted') and not facts[index].get('canary_removed'):
            container = 'aeep-'+hashlib.sha256((adapter._worker_process_id or '').encode()).hexdigest()[:32]
            await docker(worker,'exec','-i','--user','65534:65534',container,'python3','-I','-c',REMOVE_CANARY,payload={'name':canary})
            facts[index]['canary_removed'] = True

    with persist_execution_events(lambda journal_id,event:repo.put('execution_event',journal_id+':'+str(event.sequence),event)):
        try:
            journals = [EventJournal(operation) for operation in operations]
            for initial_journal in journals:
                initial_journal.append('execution.started','start')
            async with asyncio.timeout(180):
                with tempfile.TemporaryDirectory(prefix='aeep-external-answer-') as directory:
                    answer = Path(directory)/'synthetic-answer'
                    answer.write_text('synthetic external answer; never a campaign answer')
                    for index,role in enumerate(roles):
                        stage = role+':identity_policy'
                        recheck()
                        spec = getattr(definition,role)
                        config = spec.managed_host_config()
                        worker = workers[index]
                        adapter = CodexAppServerAdapter.from_executor(spec,principal_salt=service.router.store.host_principal_key())
                        adapters.append(adapter)
                        facts[index]['inspection'] = await collect(adapter,config,journals[index],recheck)
                        if not facts[index]['inspection'].get('inspection_complete') or not facts[index]['inspection'].get('identity_digest'):
                            raise ConfigurationError('worker policy inspection incomplete')
                        identity = adapter._worker_process_id
                        if identity is None:
                            raise ConfigurationError('worker process identity unavailable')
                        selected = _select_model_config(await adapter.list_models(),config)
                        if selected is None:
                            raise ConfigurationError('worker model identity unavailable')
                        stage = role+':active_policy'
                        recheck()
                        journals[index].append('action.started','active-policy-start')
                        thread_params: dict[str,Any] = {'ephemeral':True,'cwd':'/workspace','model':selected.id}
                        if not definition.schema_version.endswith('.v1'):
                            from .codex_invocation import (
                                inventory,
                                isolated_config,
                                resolve_skill_name,
                                verify_thread_inventory,
                            )
                            assert config.invocation is not None
                            catalog = await inventory(adapter.transport,'/workspace')
                            target = resolve_skill_name(catalog,config.invocation)
                            thread_params.update(permissions=worker.permissions_profile,approvalPolicy='never',approvalsReviewer='user',
                                config=isolated_config(catalog,target,
                                    verified_worker_skill=(worker.reviewed_files or {}).get(target.skill_path or '')==target.skill_sha256,
                                    reviewed_worker_files=worker.reviewed_files or {}))
                        active = await adapter.transport.request('thread/start',thread_params)
                        if not definition.schema_version.endswith('.v1'):
                            thread = active.get('thread')
                            if not isinstance(thread,dict) or not isinstance(thread.get('id'),str) or active.get('approvalsReviewer') != 'user':
                                raise ConfigurationError('task-profile permissions were not acknowledged')
                            await verify_thread_inventory(adapter.transport,thread['id'],target)
                        profile = active.get('activePermissionProfile')
                        facts[index]['active_policy'] = {'profile_matches':isinstance(profile,dict) and profile.get('id')==worker.permissions_profile and profile.get('extends') is None,
                                                        'approval_never':active.get('approvalPolicy')=='never','cwd_matches':active.get('cwd')=='/workspace'}
                        journals[index].append('action.completed','active-policy-complete')
                        stage = role+':synthetic_seed'
                        recheck()
                        journals[index].append('action.started','seed-start')
                        await worker.artifact(identity,name=markers[index],limit=100,data='c3ludGhldGlj')
                        container = 'aeep-'+hashlib.sha256(identity.encode()).hexdigest()[:32]
                        facts[index]['canary_attempted'] = True
                        cgroups = json.loads(await docker(worker,'exec','-i','--user','65534:65534',container,
                            'python3','-I','-c',SEED,payload={'name':canary}))
                        facts[index]['canary_seeded'] = True
                        if (not isinstance(cgroups,dict) or set(cgroups) != {'cpu.max','memory.max','pids.max'} or any(not isinstance(v,str)
                                or not re.fullmatch(r'(?:max|[0-9]{1,20})(?: [0-9]{1,20})?',v) for v in cgroups.values())):
                            raise ConfigurationError('malformed resource limits')
                        facts[index]['cgroups'] = cgroups
                        facts[index]['container'] = container_observation(json.loads(await docker(worker,'inspect','--format',
                            '{"image":{{json .Image}},"mounts":{{json .Mounts}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"network":{{json .HostConfig.NetworkMode}}}',container)),worker)
                        journals[index].append('action.completed','seed-complete')
                    stage = 'paired_observations'
                    for index in range(2):
                        paths = {'own_workspace':'/workspace/'+markers[index],'other_workspace':'/workspace/'+markers[1-index],
                                 'credential_canary':'/worker/auth/'+canary,'external_answer':str(answer)}
                        program = CHECK.replace('PATHS',repr(paths))
                        for old, new in zip(SKILL_PROFILES['spreadsheets:1'][:3], SKILL_PROFILES[definition.profile][:3], strict=True):
                            program = program.replace(repr(old), repr(new))
                        facts[index]['filesystem'] = filesystem_observation(await observed_command(index,'filesystem',program))
                    if definition.profile == 'spreadsheets:1':
                        dependencies = await observed_command(1,'dependencies',DEPENDENCY,30000)
                        if set(dependencies)!={'authoring_helper','artifact_tool_csv'} or any(type(v) is not bool for v in dependencies.values()):
                            raise ConfigurationError('malformed dependency observations')
                        facts[1]['dependencies'] = dependencies
                    stage = 'interruption'
                    for index,(worker,adapter) in enumerate(zip(workers,adapters,strict=True)):
                        recheck()
                        current_identity = await adapter.resolve_identity(getattr(definition,roles[index]).managed_host_config())
                        if current_identity != facts[index]['inspection']['identity_digest']:
                            raise ConfigurationError('worker identity changed during paired inspection')
                        await remove_canary(index)
                        pending = asyncio.create_task(observed_command(index,'interruption',
                            "import pathlib,time;pathlib.Path('/workspace/interruption-ready').write_text('ready');time.sleep(60)",60000))
                        for _ in range(50):
                            await asyncio.sleep(.1)
                            try:
                                await worker.artifact(adapter._worker_process_id or '',name='interruption-ready',limit=100)
                                break
                            except ConfigurationError:
                                if pending.done():
                                    raise ConfigurationError('interruption ended before readiness') from None
                        else:
                            raise ConfigurationError('interruption ready marker missing')
                        journals[index].append('cancellation.requested','interruption-cancel')
                        if not await worker.cleanup(adapter._worker_process_id or ''):
                            raise ConfigurationError('worker removal not confirmed')
                        facts[index]['cleanup_confirmed'] = True
                        try:
                            await asyncio.wait_for(pending,10)
                        except CodexProtocolError:
                            # Container removal is independently confirmed. A
                            # connection failure alone never establishes cancellation.
                            facts[index]['command_stopped'] = True
                            journals[index].append('cancellation.confirmed','interruption-stopped')
                        else:
                            raise ConfigurationError('removed worker returned a successful command')
                        pending = None
                        facts[index]['collection_complete'] = True
                    for request in requests:
                        verify_dependencies(request.executable_dependencies)
        except BaseException as exc:
            failure = exc
            result.update(failed_stage=stage,error_type=type(exc).__name__)
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending,return_exceptions=True)
            for index,adapter in enumerate(adapters):
                try:
                    await asyncio.wait_for(remove_canary(index),15)
                except Exception as exc:
                    facts[index]['cleanup_error_type'] = type(exc).__name__
                finally:
                    try:
                        await asyncio.wait_for(adapter.transport.close(),5)
                    except Exception as exc:
                        facts[index]['cleanup_error_type'] = type(exc).__name__
                    try:
                        facts[index]['cleanup_confirmed'] = bool(adapter._worker_process_id) and await asyncio.wait_for(workers[index].cleanup(adapter._worker_process_id or ''),20)
                    except Exception as exc:
                        facts[index]['cleanup_confirmed'] = False
                        facts[index]['cleanup_error_type'] = type(exc).__name__
                    if adapter._worker_security:
                        try:
                            adapter._worker_security.cleanup()
                        except OSError as exc:
                            facts[index]['cleanup_error_type'] = type(exc).__name__
            for index,(request,operation,worker) in enumerate(zip(requests,operations,workers,strict=True)):
                try:
                    named = observations(definition,roles[index],worker,facts[index])
                except (KeyError,TypeError,ValueError,ZeroDivisionError):
                    named = {}
                complete = failure is None and 'cleanup_error_type' not in facts[index] and named==expected_probes(definition,roles[index])
                facts[index]['probes_match'] = complete
                facts[index]['observed_probes'] = named
                journal = journals[index] if len(journals)>index else None
                evidence_digest = None
                probe_digests = []
                if journal is not None:
                    for name,value in named.items():
                        journal.append('artifact.created','probe-'+name,evidence_ref=content_digest(value))
                    journal.append('artifact.created','observations',evidence_ref=content_digest(facts[index]))
                    journal.append('execution.completed' if complete else 'execution.failed','terminal')
                    evidence = journal.evidence(getattr(definition,roles[index]).managed_host_config().adapter_id,
                        RawExecution(status=ExecutionStatus.SUCCESS if complete else ExecutionStatus.FAILED,
                            metadata={'boundary_digest':worker.digest(),'host_runtime_digest':facts[index].get('inspection',{}).get('identity_digest')}))
                    evidence_digest = repo.put('execution_evidence',evidence.digest(),evidence)
                    for name,value in named.items():
                        recorded_probe = BoundaryProbe(probe_id=new_id('probe'),name=name,implementation_digest=content_digest(probe_definitions[index][name]),
                            worker_digest=worker.digest(),execution_evidence_digest=evidence_digest,observed=value)
                        probe_digests.append(repo.put('boundary_probe',recorded_probe.probe_id,recorded_probe))
                record = WorkerInspectionResult(request_id=request.plan_id,worker_digest=worker.digest(),
                    execution_evidence_digest=evidence_digest,observations=facts[index])
                repo.put('worker_pair_inspection',operation,record)
                repo.finish_operation(operation,elapsed_seconds=time.perf_counter()-reserved[index][1])
                result['workers'][roles[index]] = {'record_digest':content_digest(record),'probe_digests':probe_digests,'probes_match':complete}
    result['probes_match'] = all(value['probes_match'] for value in result['workers'].values())
    if isinstance(failure,(asyncio.CancelledError,KeyboardInterrupt,SystemExit)):
        raise failure
    return result


async def inspect_dynamic_declaration(adapter: CodexAppServerAdapter, *,
                                      config: Any, worker: ManagedWorkerBinding,
                                      binding: Any, journal: EventJournal,
                                      recheck: Any) -> dict[str, Any]:
    """Zero-turn declaration/policy observation; never model-exposure evidence.

    The canonical composed probe owner must authorize the binding and operation
    before this function. This function neither registers authority nor invokes
    a callback. Legacy paired inspection does not call it.
    """
    from .codex_app_server import _select_model_config
    from .codex_dynamic_tools import CodexDynamicTools
    from .codex_invocation import inventory, isolated_config, verify_thread_inventory

    target = config.invocation
    if (not isinstance(binding, CodexDynamicTools) or target is None
            or target.dynamic_tools_digest != binding.digest
            or not adapter.transport.options.experimental_api):
        raise ConfigurationError('composed declaration identity unavailable')
    recheck()
    binding.verify(target.dynamic_tools_digest, worker.digest())
    selected = _select_model_config(await adapter.list_models(), config)
    if selected is None:
        raise ConfigurationError('composed worker model metadata unavailable')
    catalog = await inventory(adapter.transport, '/workspace')
    journal.append('action.started', 'dynamic-declaration-start',
                   action_digest=content_digest(binding.definition()))
    # No handler is installed: declaration inspection has no task-call authority.
    response = await adapter.transport.request('thread/start', {
        'ephemeral': True, 'cwd': '/workspace', 'model': selected.id,
        'permissions': worker.permissions_profile, 'approvalPolicy': 'never',
        'approvalsReviewer': 'user',
        'config': isolated_config(catalog, target,
            reviewed_worker_files=worker.reviewed_files or {}),
        'dynamicTools': binding.declarations(),
    })
    thread = response.get('thread')
    if (not isinstance(thread, dict) or not isinstance(thread.get('id'), str)
            or not thread['id'] or response.get('approvalsReviewer') != 'user'):
        raise ConfigurationError('composed declaration response malformed')
    await verify_thread_inventory(adapter.transport, thread['id'], target)
    recheck()
    binding.verify(target.dynamic_tools_digest, worker.digest())
    profile = response.get('activePermissionProfile')
    journal.append('action.completed', 'dynamic-declaration-complete')
    return {
        'binding_digest': binding.digest,
        'declaration_digest': content_digest({'dynamicTools': binding.declarations()}),
        'declaration_bytes': len(json.dumps(binding.declarations(), separators=(',', ':'), allow_nan=False).encode()),
        'declaration_acknowledged': True,
        'model_tool_exposure': 'unknown',
        'model_turns': 0,
        'task_calls': 0,
        'active_policy': {
            'profile_matches': isinstance(profile, dict) and profile.get('id') == worker.permissions_profile and profile.get('extends') is None,
            'approval_never': response.get('approvalPolicy') == 'never',
            'cwd_matches': response.get('cwd') == '/workspace',
        },
    }


async def inspect_scripted_callback(transport: Any, *, binding: Any,
                                    worker_digest: str, outer_attempt_id: str,
                                    journal: EventJournal, recheck: Any,
                                    timeout_seconds: float) -> dict[str, Any]:
    """Exercise the existing callback parser over a reviewed scripted transport.

    Caller owns its exact fixture executable binding and canonical conformance
    reservation. This cannot establish a native AppServer-issued tool call.
    """
    from ..models import SideEffect
    from .codex_dynamic_tools import DynamicToolSession

    if (not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool)
            or not 0 < timeout_seconds <= 60):
        raise ConfigurationError('scripted callback inspection timeout invalid')
    recheck()
    active = DynamicToolSession(binding, worker_digest=worker_digest,
        expected_digest=binding.digest,
        approved_side_effect=SideEffect(binding.identity['approval_ceiling']),
        max_bytes=16384, deadline=asyncio.get_running_loop().time()+timeout_seconds,
        outer_attempt_id=outer_attempt_id, journal=journal)
    terminal = asyncio.get_running_loop().create_future()
    def event(method: str, params: dict[str, Any]) -> None:
        if method == 'fixture/callback-result' and not terminal.done():
            terminal.set_result(params)
    unsubscribe = transport.subscribe(event)
    transport.dynamic_tool_handler = active.call
    import contextvars
    transport.dynamic_tool_context = contextvars.copy_context()
    try:
        async with asyncio.timeout(timeout_seconds):
            thread = await transport.request('thread/start', {'dynamicTools': binding.declarations()})
            active.bind_thread(thread['thread']['id'])
            turn = await transport.request('fixture/callback', {})
            active.bind_turn(turn['turn']['id'])
            result = await terminal
            if not isinstance(result, dict) or set(result) != {'response_success'} or type(result['response_success']) is not bool:
                raise ConfigurationError('scripted callback result malformed')
            recheck()
            return {'provenance': 'reviewed_scripted_transport', 'model_turns': 0,
                'native_host_issued_callback': 'unobserved',
                'binding_digest': binding.digest,
                'response_success': result['response_success'],
                'completed_tools': sorted(active.tools_succeeded),
                'callback_evidence': active.evidence}
    finally:
        active.close()
        try:
            await transport.cancel_dynamic_tools()
        finally:
            unsubscribe()
            transport.dynamic_tool_handler = None
            transport.dynamic_tool_context = None


class ComposedPairDefinition(StrictModel):
    """Additive composition identity; historical worker-pair schemas are unchanged."""
    schema_version: Literal['assessment.composed-pair-inspection.v1'] = 'assessment.composed-pair-inspection.v1'
    control: ExecutorSpec
    treatment: ExecutorSpec
    differential: DifferentialEnvironment
    shared_versions: dict[str, str]
    callback_bindings: dict[Digest, Digest]
    native_backends: dict[Digest, Digest]

    @model_validator(mode='after')
    def exact_composition(self) -> ComposedPairDefinition:
        workers = []
        configs = []
        if set(self.shared_versions) != {'pandas', 'openpyxl'}:
            raise ValueError('composed inspection requires exact shared workbook versions')
        for role in ('control', 'treatment'):
            spec = getattr(self, role)
            config = spec.managed_host_config()
            worker = binding_from_config(config.managed_worker)
            target = config.invocation
            if (worker is None or target is None or config.adapter_id.split(':', 1)[0] != 'codex-app-server'
                    or config.argv != (worker.binary, 'app-server') or not worker.model_proxy_url
                    or not worker.credential_volume or config.store_prompt or config.store_output
                    or target.dynamic_tools_digest != self.callback_bindings.get(worker.digest())
                    or target.mode != ('turn' if role == 'control' else 'dynamic_tool')
                    or target.local_profile != 'capable_local' or config.artifact is None
                    or not self.native_backends.get(worker.digest())):
                raise ValueError('composed inspection requires exact worker/callback/native profiles')
            workers.append(worker)
            configs.append(config)
        validate_worker_pair(*workers)
        targets = [config.invocation for config in configs]
        assert targets[0] is not None and targets[1] is not None
        if (targets[0].native_catalog != targets[1].native_catalog
                or targets[0].supporting_skills != targets[1].supporting_skills
                or targets[0].supporting_tools != targets[1].supporting_tools):
            raise ValueError('composed profiles require identical shared capabilities')
        keys = {worker.digest() for worker in workers}
        if set(self.callback_bindings) != keys or set(self.native_backends) != keys:
            raise ValueError('composed identity maps must cover exactly the selected workers')
        if configs[0].model_dump(exclude={'adapter_id', 'managed_worker', 'invocation'}) != configs[1].model_dump(exclude={'adapter_id', 'managed_worker', 'invocation'}):
            raise ValueError('composed profiles require equivalent shared executor settings')
        return self


def protected_callback_evidence(repository: Any, task_router: Any,
                                scripted_result: dict[str, Any]) -> dict[str, Any]:
    """Resolve linked canonical child evidence; never infer missing receipts."""
    from ..assessment.models import content_digest
    links = scripted_result.get('callback_evidence', [])
    if not isinstance(links, list) or len(links) > 64:
        raise ConfigurationError('callback evidence links malformed')
    references = {item['evidence_ref'] for item in links
        if isinstance(item, dict) and isinstance(item.get('evidence_ref'), str)}
    states = []
    receipt_count = 0
    scope_digests = set()
    for reference in references:
        evidence = repository.get('callback_evidence', reference)
        claim = repository.get('callback_claim', evidence['claim_digest'])
        if (claim.get('context_kind') != 'conformance'
                or evidence.get('task_scope_digest') != claim.get('task_scope_digest')
                or evidence.get('resources_overlap_outer_trial') is not True):
            raise ConfigurationError('callback canonical evidence differs')
        if (claim.get('binding_digest') != scripted_result.get('binding_digest')
                or claim.get('task_scope_digest') != task_router._task_scope_digest):
            raise ConfigurationError('callback binding or current scope differs')
        action_id = 'dynamic_' + claim['call_digest']
        with task_router.store._lock:
            attempts = [json.loads(row[0]) for row in task_router.store._connection.execute(
                'SELECT a.payload_json FROM execution_attempts a JOIN decisions d ON d.decision_id=a.decision_id WHERE d.action_id=?', (action_id,))]
            receipts = [json.loads(row[0]) for row in task_router.store._connection.execute(
                'SELECT payload_json FROM receipts WHERE action_id=?', (action_id,))]
        if len(attempts) > 32 or len(receipts) > 32:
            raise ConfigurationError('callback child evidence exceeds fixed bound')
        attempt_map = {content_digest(item): item for item in attempts}
        receipt_map = {content_digest(item): item for item in receipts}
        scope_digests.add(claim['task_scope_digest'])
        for digest in evidence['child_attempt_digests']:
            if digest not in attempt_map:
                raise ConfigurationError('callback child attempt is unavailable')
            if attempt_map[digest].get('task_scope_digest') != claim['task_scope_digest']:
                raise ConfigurationError('callback child attempt scope differs')
            states.append(attempt_map[digest]['state'])
        for digest in evidence['child_receipt_digests']:
            if digest not in receipt_map:
                raise ConfigurationError('callback child receipt is unavailable')
            receipt_count += 1
    return {'canonical_link_count': len(references), 'child_attempt_states': states,
        'child_receipt_count': receipt_count, 'task_scope_digests': sorted(scope_digests),
        'provenance': scripted_result.get('provenance'),
        'native_host_issued_callback': 'unobserved', 'full_conformance': False}


def verify_composed_binding(repository: Any, record: Any, worker_digest: str) -> ExecutorSpec:
    if record.adapter.split(':', 1)[0] != 'codex-app-server':
        raise ConfigurationError('composed conformance adapter is unsupported')
    document = repository.get('codex_dynamic_tools', record.callback_binding_digest)
    identity = document.get('identity', {})
    from .codex_dynamic_tools import CodexDynamicTools
    if (identity.get('implementation_digest') != CodexDynamicTools.implementation_digest()
            or content_digest(document) != record.callback_binding_digest
            or identity.get('worker_digest') != worker_digest
            or identity.get('native_backend_digest') != record.native_backend_digest):
        raise ConfigurationError('composed callback backend or worker binding differs')
    composite = repository.get('composed_pair_definition', record.composed_definition_digest)
    if (composite.get('callback_bindings', {}).get(worker_digest) != record.callback_binding_digest
            or composite.get('native_backends', {}).get(worker_digest) != record.native_backend_digest):
        raise ConfigurationError('composed definition does not bind selected callback/native worker')
    from ..hosts.workers import binding_from_config
    composed = ComposedPairDefinition.model_validate(composite)
    profiles = [composed.control, composed.treatment]
    selected = [spec for spec in profiles if (bound := binding_from_config(spec.managed_host_config().managed_worker)) is not None and bound.digest() == worker_digest]
    if len(selected) != 1:
        raise ConfigurationError('composed profile identity is missing or ambiguous')
    target = selected[0].managed_host_config().invocation
    if target is None or target.dynamic_tools_digest != record.callback_binding_digest:
        raise ConfigurationError('composed profile identity is missing or ambiguous')
    if content_digest(composite) != record.composed_definition_digest:
        raise ConfigurationError('composed inspection definition differs')
    with repository.store._lock:
        for required_review in (record.callback_binding_digest, record.composed_definition_digest):
            reviewed = repository.store._connection.execute(
                'SELECT revoked FROM assessment_reviews WHERE digest=?', (required_review,)).fetchone()
            if reviewed is None or reviewed[0]:
                raise ConfigurationError('composed boundary requires current exact review')
    return selected[0]


def verify_composed_callback(repository: Any, record: Any, probe: Any, definition: Any,
                             evidence: Any, selected_spec: ExecutorSpec) -> None:
    identity = repository.get('codex_dynamic_tools', record.callback_binding_digest)['identity']
    identity_digest = record.identity_digest
    from ..economic.prepared import executor_fingerprint
    from ..models import ExecutionReceipt
    if probe.host_receipt_digest is None:
        raise ConfigurationError('actual callback host receipt is missing')
    host_receipt = ExecutionReceipt.model_validate(repository.get('conformance_host_receipt', probe.host_receipt_digest))
    if (content_digest(host_receipt) != probe.host_receipt_digest
            or host_receipt.executor_fingerprint != executor_fingerprint(selected_spec)
            or host_receipt.metadata.get('host_runtime_digest') != identity_digest
            or host_receipt.metadata.get('dynamic_tools_digest') != record.callback_binding_digest
            or host_receipt.status is not ExecutionStatus.SUCCESS
            or host_receipt.metadata.get('dynamic_cleanup_confirmed') is not True
            or host_receipt.metadata.get('model_turn_count') != 1
            or not host_receipt.accounting.model_usage):
        raise ConfigurationError('callback host receipt is not the pinned actual process identity')
    invocation = definition.executor.managed_host_config().invocation if definition.executor.kind.value == 'host_managed' else None
    if (invocation is None or invocation.dynamic_tools_digest != record.callback_binding_digest
            or probe.observed.get('callback_origin') != 'native_app_server'
            or probe.observed.get('native_callback_observed') is not True
            or not any(event.kind == 'action.completed' and isinstance(event.source_id, str) and event.source_id.startswith(('dynamic-complete:', 'adapter:dynamic-complete:')) for event in evidence.events)
            or not any(event.accounting is not None and event.accounting.model_usage for event in evidence.events)):
        raise ConfigurationError('full composed conformance requires an actual model-issued native callback')
    links = [event.evidence_ref for event in evidence.events
             if isinstance(event.source_id, str) and event.source_id.startswith(('dynamic-link:', 'adapter:dynamic-link:')) and event.evidence_ref is not None]
    if not links:
        raise ConfigurationError('native callback lacks durable child evidence')
    for reference in links:
        child = repository.get('callback_evidence', reference)
        claim = repository.get('callback_claim', child['claim_digest'])
        if (content_digest(child) != reference
                or content_digest(claim) != child['claim_digest']
                or not any(event.action_digest == claim.get('call_digest') and event.evidence_ref == reference for event in evidence.events)
                or not any(event.kind == 'action.completed' and event.action_digest == claim.get('call_digest') for event in evidence.events)
                or claim.get('context_kind') != 'conformance' or claim.get('model_turn_allowance') != 1
                or claim.get('binding_digest') != record.callback_binding_digest
                or child.get('task_scope_digest') != claim.get('task_scope_digest')
                or not child.get('child_attempt_digests') or not child.get('child_receipt_digests')):
            raise ConfigurationError('native callback evidence is not bound to a model conformance allowance')
        from ..attempts import ExecutionAttempt
        request = ConformanceProbeRequest.model_validate(repository.get('conformance_request', claim['request_digest']))
        operation = repository.get('operation_start', claim['operation_reference'])
        outer = ExecutionAttempt.model_validate(repository.get('callback_outer_attempt', claim['outer_attempt_reference']))
        from .codex_invocation import contract_digest
        if (content_digest(outer) != claim['outer_attempt_reference']
                or content_digest(operation) != claim['operation_reference']
                or contract_digest({'attempt_id': outer.attempt_id}) != claim.get('outer_attempt_digest')
                or content_digest(request) != claim['request_digest']
                or request.schema_version != 'assessment.conformance-request.v4'
                or request.operation != 'composed_pair_inspection' or request.composed_model_turns != 1
                or request.pair_definition_digest != record.composed_definition_digest
                or record.callback_binding_digest not in request.definition_digests
                or operation.get('plan_id') != request.plan_id or operation.get('stage') != 'composed_pair_inspection'
                or operation.get('reserved', {}).get('max_model_turns') != 1
                or evidence.attempt_id != outer.attempt_id
                or outer.state.value != 'INVOKING'
                or outer.executor_id != selected_spec.id
                or host_receipt.executor_id != selected_spec.id
                or outer.decision_id != host_receipt.decision_id
                or outer.executor_fingerprint != host_receipt.executor_fingerprint):
            raise ConfigurationError('native callback request/reservation/host attempt lineage differs')
        repository.authorize(request)
        from ..assessment.identity import verify_dependencies
        verify_dependencies(request.executable_dependencies)
        from ..models import TaskScope
        scope = TaskScope.model_validate(repository.get('callback_task_scope', child['task_scope_reference']))
        limits = identity.get('scope_limits', {})
        from ..models import SideEffect
        if (content_digest(scope) != child['task_scope_digest']
                or scope.executor_fingerprints != identity.get('executor_fingerprints')
                or scope.max_attempts > limits.get('max_attempts', 0)
                or scope.max_attempt_seconds > limits.get('max_attempt_seconds', 0)
                or scope.approval_ceiling.rank > SideEffect(identity['approval_ceiling']).rank):
            raise ConfigurationError('native callback scope evidence differs')
        from .codex_sandbox import NativeSandboxConfig, native_backend_digest
        native_specs = {name: ExecutorSpec.model_validate(repository.get('callback_child_executor', reference))
                        for name, reference in child.get('child_executor_digests', {}).items()}
        if set(native_specs) != set(scope.executor_fingerprints):
            raise ConfigurationError('callback native executor mapping is incomplete')
        backends = {}
        for name, executor in native_specs.items():
            boundary = NativeSandboxConfig.model_validate(executor.config.get('native_sandbox', {}))
            if (content_digest(executor) != child['child_executor_digests'][name]
                    or executor_fingerprint(executor) != scope.executor_fingerprints[name]
                    or executor.kind is not ExecutorKind.COMMAND
                    or not executor.config.get('argv_literal') or not boundary.single_process):
                raise ConfigurationError('callback native executor binding differs')
            boundary.validate_single_process()
            boundary.argv([])  # Offline policy compilation and streamed native-binary pin check.
            backends[name] = native_backend_digest(boundary)
        if contract_digest(backends) != record.native_backend_digest:
            raise ConfigurationError('callback actual aggregate native backend differs')
        attempts = [ExecutionAttempt.model_validate(repository.get('callback_child_attempt', item)) for item in child['child_attempt_digests']]
        receipts = [ExecutionReceipt.model_validate(repository.get('callback_child_receipt', item)) for item in child['child_receipt_digests']]
        if any(content_digest(item) != expected for item, expected in zip(attempts, child['child_attempt_digests'], strict=True)) or any(content_digest(item) != expected for item, expected in zip(receipts, child['child_receipt_digests'], strict=True)):
            raise ConfigurationError('callback child canonical digest differs')
        for receipt in receipts:
            if receipt.action_id != 'dynamic_' + claim['call_digest']:
                raise ConfigurationError('callback child action differs')
            matching = [item for item in attempts if item.decision_id == receipt.decision_id
                        and item.task_scope_digest == child['task_scope_digest']
                        and receipt.receipt_id in item.terminal_receipt_ids
                        and item.executor_fingerprint == receipt.executor_fingerprint]
            if len(matching) != 1 or scope.executor_fingerprints.get(receipt.executor_id) != receipt.executor_fingerprint:
                raise ConfigurationError('callback child receipt does not match the scoped canonical attempt')
            from .codex_sandbox import NativeSandboxConfig, native_backend_digest
            executor_reference = child.get('child_executor_digests', {}).get(receipt.executor_id)
            executor = ExecutorSpec.model_validate(repository.get('callback_child_executor', executor_reference or ''))
            boundary = NativeSandboxConfig.model_validate(executor.config.get('native_sandbox', {}))
            if (content_digest(executor) != executor_reference
                    or executor_fingerprint(executor) != receipt.executor_fingerprint
                    or executor.kind is not ExecutorKind.COMMAND
                    or not executor.config.get('argv_literal') or not boundary.single_process
                    or receipt.metadata.get('enforcement_backend_digest') != native_backend_digest(boundary)):
                raise ConfigurationError('callback child native backend evidence differs')
            boundary.validate_single_process()

