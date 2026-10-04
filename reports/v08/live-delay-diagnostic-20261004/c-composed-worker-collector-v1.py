"""Finite C worker component observations; no conformance or admission.

Adapted from collect-composed-workers-5fff.py. The two B roles retain the same
physical Spreadsheets skill and supporting inventory; only the reviewed dynamic
tool inventory may differ. This file has no main entry point and must only be
called under its exact reviewed requests.
"""
from typing import Literal
from aeep.hosts.codex_pair_inspection import *
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.models import StrictModel
from aeep.assessment.identity import file_digest, runtime_dependencies
from aeep.assessment.verification import verification_source_digest
SOURCE="e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
SOURCE_PIN_STATUS="diagnostic_source_freeze_2026-10-04"


def expected_common_inventory(spreadsheets):
    alias_name, = spreadsheets.alias_paths
    return {
        'spreadsheets_bundle': content_digest(spreadsheets),
        'skill:'+alias_name: spreadsheets.skill_sha256,
    }


class SharedSpreadsheetsDefinition(StrictModel):
    """Exact common physical Spreadsheets image/files/runtime expectation."""
    schema_version: Literal['assessment.b-shared-spreadsheets.v1'] = 'assessment.b-shared-spreadsheets.v1'
    image_digest: str
    skill_path: str
    alias_path: str
    runtime_path: str
    skill_sha256: str
    alias_paths: dict[str, str]
    shared_versions: dict[str, str]
    dependency_expectations: dict[str, bool]

    @model_validator(mode='after')
    def exact_profile(self):
        skill_path, alias_path, runtime_path, names = SKILL_PROFILES['spreadsheets:1']
        if (not re.fullmatch(r'sha256:[a-f0-9]{64}', self.image_digest)
                or (self.skill_path, self.alias_path, self.runtime_path) != (skill_path, alias_path, runtime_path)
                or not re.fullmatch(r'[a-f0-9]{64}', self.skill_sha256)
                or len(self.alias_paths) != 1 or not set(self.alias_paths).issubset(names)
                or set(self.alias_paths.values()) != {skill_path}
                or set(self.shared_versions) != {'pandas', 'openpyxl'}
                or set(self.dependency_expectations) != {'authoring_helper', 'artifact_tool_csv'}
                or any(value is not True for value in self.dependency_expectations.values())):
            raise ValueError('B requires the exact reviewed shared Spreadsheets profile')
        return self

class WorkerComponentDefinition(StrictModel):
    schema_version: Literal['assessment.b-composed-worker-component.v1'] = 'assessment.b-composed-worker-component.v1'
    composed: ComposedPairDefinition
    common_inventory: dict[str, Digest]
    spreadsheets: SharedSpreadsheetsDefinition

    @property
    def control(self): return self.composed.control
    @property
    def treatment(self): return self.composed.treatment
    @property
    def differential(self): return self.composed.differential
    @property
    def shared_versions(self): return self.composed.shared_versions
    @property
    def profile(self): return 'spreadsheets:1'
    @property
    def candidate_skill_digest(self): return self.spreadsheets.skill_sha256

    @model_validator(mode='after')
    def exact_shared_inventory(self):
        if self.common_inventory != expected_common_inventory(self.spreadsheets):
            raise ValueError('B common inventory must bind the shared Spreadsheets bundle and skill digest')
        for role in ('control','treatment'):
            target=getattr(self.composed,role).managed_host_config().invocation
            if (target is None or target.native_catalog is not False or target.supporting_tools
                    or {item.name:item.path for item in target.supporting_skills} != self.spreadsheets.alias_paths
                    or any(item.sha256 != self.spreadsheets.skill_sha256 for item in target.supporting_skills)):
                raise ValueError('B shared profile must contain only the exact Spreadsheets support')
        return self


def expected_component_probes(definition, role, binding):
    """Exact supporting probes; candidate_access is the dynamic-tool delta."""
    candidates = definition.differential.candidate_dynamic_tools
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
        'candidate_access': {
            'definition_digest':content_digest(definition.differential),
            'candidate_available':role == 'treatment',
            'candidate_kind':'dynamic_tool',
            'candidate_tools_digest':content_digest(candidates),
            'callback_binding_digest':binding.digest,
        },
    }


def authorize_component(service, control_request, treatment_request, bindings):
    import aeep.router
    root=Path(aeep.router.__file__).resolve().parents[2]
    if verification_source_digest(root)!=SOURCE:raise ConfigurationError("renew current-source component review")
    repo=service.repository
    requests=[ConformanceProbeRequest.model_validate(repo.get('conformance_request',i)) for i in (control_request,treatment_request)]
    if (len(bindings)!=2 or any(not isinstance(b,CodexDynamicTools) for b in bindings)
            or any(r.operation!='composed_pair_inspection' or r.composed_model_turns!=0 for r in requests)
            or requests[0].plan_id==requests[1].plan_id
            or requests[0].pair_definition_digest!=requests[1].pair_definition_digest
            or requests[0].authorization_id!=requests[1].authorization_id
            or requests[0].subject_digest!=requests[1].subject_digest
            or requests[0].recipe_digest!=requests[1].recipe_digest
            or requests[0].environment_digest!=requests[1].environment_digest):
        raise ConfigurationError('two exact zero-turn composed requests required')
    definitions=[];workers=[];component=None
    for index,(role,request) in enumerate(zip(('control','treatment'),requests,strict=True)):
        grant=repo.authorize(request);verify_dependencies(request.executable_dependencies)
        required=runtime_dependencies();required[str(Path(__file__).resolve())]=file_digest(Path(__file__).resolve())
        if request.executable_dependencies!=required:raise ConfigurationError('component executable identity missing/changed')
        mapping=BoundaryProbeDefinition.model_validate(repo.get('boundary_probe_definition',request.mapping_digest))
        digest=mapping.expected.get('component_digest')
        current=WorkerComponentDefinition.model_validate(repo.get('composed_worker_component',digest))
        if (content_digest(current)!=digest or digest not in request.definition_digests
                or content_digest(current.spreadsheets) not in request.definition_digests
                or current.differential.shared_definition_digest not in request.definition_digests
                or current.common_inventory != expected_common_inventory(current.spreadsheets)
                or current.composed!=ComposedPairDefinition.model_validate(repo.get('composed_pair_definition',request.pair_definition_digest))):
            raise ConfigurationError('component/composed definition differs')
        if component is not None and component!=current:raise ConfigurationError('paired component differs')
        component=current
        spec=getattr(current,role);worker=binding_from_config(spec.managed_host_config().managed_worker)
        if (worker is None or worker.digest()!=request.worker_digest or mapping.executor!=spec
                or mapping.name!='worker_pair_inspection' or content_digest(mapping)!=request.mapping_digest):
            raise ConfigurationError('actual selected worker/component mapping differs')
        binding=bindings[index];document=repo.get('codex_dynamic_tools',binding.digest)
        if (document!=binding.definition() or binding.digest!=current.composed.callback_bindings[worker.digest()]
                or binding.identity['native_backend_digest']!=current.composed.native_backends[worker.digest()]):
            raise ConfigurationError('actual callback declaration differs')
        differential=current.composed.differential
        target=spec.managed_host_config().invocation
        if (not differential.candidate_dynamic_tools or differential.candidate_paths or differential.candidate_aliases
                or differential.candidate_inventory!=differential.candidate_dynamic_tools or target is None
                or (role=='treatment' and differential.candidate_dynamic_tools != {
                    f'dynamic:{target.server}:{target.tool}':target.tool_sha256})
                or (role=='control' and target.mode!='turn')):
            raise ConfigurationError('B candidate must be the exact dynamic callback-only difference')
        with repo.store._lock:
            for required in (digest,request.pair_definition_digest,binding.digest,
                             content_digest(current.spreadsheets),current.differential.shared_definition_digest):
                review=repo.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',(required,)).fetchone()
                if review is None or review[0]:raise ConfigurationError('component definition review absent/revoked')
        binding.verify(binding.digest,worker.digest())
        common = current.common_inventory
        role_inventory = binding.inventory()
        if set(common) & set(role_inventory):
            raise ConfigurationError('common and callback inventories overlap')
        expected_effective = {**common, **role_inventory}
        reviewed_effective = current.differential.control_inventory if role == 'control' else current.differential.treatment_inventory
        if expected_effective != reviewed_effective:
            raise ConfigurationError('reviewed effective inventory is not common inventory plus exact callback')
        require_destination(spec,AssessmentEnvironment.model_validate(repo.get('environment',request.environment_digest)),grant)
        probes={}
        for name,expected in expected_component_probes(current,role,binding).items():
            probe=BoundaryProbeDefinition(name=name,executor=spec,expected=expected)
            if (content_digest(probe) not in request.definition_digests
                    or repo.get('boundary_probe_definition',content_digest(probe))!=probe.model_dump(mode='json')):
                raise ConfigurationError('exact worker probe definition not reviewed')
            probes[name]=probe
        definitions.append(probes);workers.append(worker)
    validate_worker_pair(*workers)
    expected_files = {component.spreadsheets.skill_path:component.spreadsheets.skill_sha256}
    if (workers[0].image != workers[1].image
            or workers[0].image != component.spreadsheets.image_digest
            or workers[0].reviewed_files != expected_files
            or workers[1].reviewed_files != expected_files
            or component.shared_versions != component.spreadsheets.shared_versions
            or bindings[1].inventory() != {**bindings[0].inventory(), **component.differential.candidate_dynamic_tools}):
        raise ConfigurationError('B roles do not share the exact reviewed physical Spreadsheets image')
    return component,requests,workers,definitions


def physical_spreadsheets_observation(definition, role, facts, catalog):
    """Require identical measured physical skill and enabled support inventory."""
    sheet = definition.spreadsheets
    spec = getattr(definition, role)
    target = spec.managed_host_config().invocation
    worker = binding_from_config(spec.managed_host_config().managed_worker)
    if target is None or worker is None:
        raise ConfigurationError('B physical inventory lacks its reviewed worker target')
    filesystem = facts['filesystem']
    if (filesystem.get('candidate_skill_sha256') != sheet.skill_sha256
            or filesystem.get('candidate_alias') is not True
            or filesystem.get('candidate_runtime') is not True
            or filesystem.get('shared_workbook_roundtrip') is not True
            or any(filesystem.get(name) != version for name,version in sheet.shared_versions.items())):
        raise ConfigurationError('shared physical Spreadsheets filesystem probe differs')
    configured_sheet = {item.name:item.path for item in target.supporting_skills
                        if item.name in sheet.alias_paths}
    if (configured_sheet != sheet.alias_paths
            or worker.reviewed_files != {sheet.skill_path:sheet.skill_sha256}):
        raise ConfigurationError('Spreadsheets skill is not the exact configured shared support')
    if not isinstance(catalog,dict) or not isinstance(catalog.get('skills'),list):
        raise ConfigurationError('actual enabled skill inventory is unavailable')
    enabled = []
    for skill in catalog['skills']:
        if (not isinstance(skill,dict) or type(skill.get('enabled')) is not bool
                or not isinstance(skill.get('name'),str) or not isinstance(skill.get('path'),str)):
            raise ConfigurationError('actual skill inventory entry is malformed')
        if skill.get('enabled') is True:
            dependencies = skill.get('dependencies') or {}
            if not isinstance(dependencies,dict):
                raise ConfigurationError('enabled skill dependencies are malformed')
            enabled.append({'name':skill.get('name'),'path':skill.get('path'),
                            'dependencies_digest':content_digest(dependencies)})
    expected = [{'name':item.name,'path':item.path} for item in target.supporting_skills]
    actual_identities = [{'name':item['name'],'path':item['path']} for item in enabled]
    if sorted(actual_identities,key=lambda item:(str(item['path']),str(item['name']))) != sorted(expected,key=lambda item:(str(item['path']),str(item['name']))):
        raise ConfigurationError('actual enabled skill inventory differs from exact supporting profile')
    spreadsheet_entries = [item for item in enabled if item['name'] in sheet.alias_paths]
    observed_aliases = {item['name']:item['path'] for item in spreadsheet_entries}
    if (observed_aliases != sheet.alias_paths
            or any(path not in {sheet.skill_path,sheet.alias_path} for path in observed_aliases.values())):
        raise ConfigurationError('enabled Spreadsheets aliases differ from reviewed paths')
    summary = facts['inspection'].get('advertised_inventory',{})
    if (not isinstance(summary,dict) or not isinstance(summary.get('apps'),list)
            or not isinstance(summary.get('servers'),list)):
        raise ConfigurationError('advertised worker inventory is unavailable')
    target_tools = {}
    for item in target.supporting_tools:
        target_tools.setdefault(item.server,[]).append(item.tool)
    expected_servers = {name:sorted(names) for name,names in target_tools.items()}
    actual_servers = {}
    for item in summary.get('servers',[]):
        if (not isinstance(item,dict) or not isinstance(item.get('name'),str)
                or not isinstance(item.get('tool_names'),list) or item.get('complete') is not True
                or item['name'] in actual_servers):
            raise ConfigurationError('advertised server inventory is incomplete')
        actual_servers[item['name']] = sorted(item['tool_names'])
    if (any(not isinstance(item,dict) or item.get('enabled') is True or item.get('callable') is True
                   for item in summary['apps'])
            or actual_servers != expected_servers):
        raise ConfigurationError('unreviewed app or server inventory is enabled')
    dependencies = facts.get('dependencies')
    if dependencies != sheet.dependency_expectations:
        raise ConfigurationError('shared Spreadsheets dependency probe differs')
    return {
        'image_digest':worker.image,
        'skill_path':sheet.skill_path,
        'skill_sha256':filesystem['candidate_skill_sha256'],
        'alias_path':sheet.alias_path,
        'aliases':observed_aliases,
        'runtime_path':sheet.runtime_path,
        'runtime_present':filesystem['candidate_runtime'],
        'versions':{name:filesystem[name] for name in sorted(sheet.shared_versions)},
        'dependencies':dependencies,
        'enabled_skills':sorted(enabled,key=lambda item:(str(item['path']),str(item['name']))),
        'supporting_servers':actual_servers,
        'disabled_apps':sorted(summary.get('apps',[]),key=lambda item:str(item.get('id'))),
    }


def composed_observations(definition,role,worker,facts,binding):
    # The adapter helper validates the exact declaration, active policy and
    # zero-turn boundary; it does not establish model exposure or use.
    candidate_access = dynamic_candidate_access_observation(definition.differential,
        binding=binding,worker=worker,declaration=facts['dynamic_declaration'])
    expected = expected_component_probes(definition,role,binding)
    named = {name:dict(value) for name,value in expected.items()}
    named['candidate_access'] = candidate_access
    inspect=facts['inspection']; observed=facts['filesystem']; cgroups=facts['cgroups']; meta=facts['container']
    quota,period=map(int,cgroups['cpu.max'].split())
    support = facts['physical_spreadsheets']
    disabled=inspect.get('config/read',{}); requirements=inspect.get('configRequirements/read',{})
    active=facts['active_policy']
    mount=[m for m in meta['mounts'] if m.get('Type') in {'volume','bind'}]
    mount_ok=(len(mount)==1 and mount[0].get('Type')=='volume'
              and mount[0].get('Name')==worker.credential_volume and mount[0].get('Destination')=='/worker/auth')
    named.update({
        'allowed_tool': {'workspace_write':inspect['sandbox_command']['workspace_write'] is True,
                         'dependencies':support['dependencies']==definition.spreadsheets.dependency_expectations
                             and observed['shared_workbook_roundtrip'] is True
                             and all(support['versions'].get(k)==v for k,v in definition.shared_versions.items())},
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
    })
    observed_common = {
        'spreadsheets_bundle':content_digest(definition.spreadsheets),
        **{'skill:'+name: facts['physical_spreadsheets']['skill_sha256']
           for name in definition.spreadsheets.alias_paths},
    }
    if observed_common != definition.common_inventory:
        raise ConfigurationError('observed shared skill digest differs from the reviewed common inventory')
    effective = {**observed_common, **facts['dynamic_declaration']['dynamic_inventory']}
    expected_effective = definition.differential.control_inventory if role=='control' else definition.differential.treatment_inventory
    if effective != expected_effective:
        raise ConfigurationError('observed effective inventory differs from the reviewed common plus callback inventory')
    facts['effective_inventory'] = effective
    facts['common_inventory'] = observed_common
    facts['candidate_access'] = candidate_access
    return named

async def execute_composed_workers(service: AssessmentService, control_request: str, treatment_request: str, *, bindings: tuple[CodexDynamicTools, CodexDynamicTools]) -> dict[str, Any]:
    """One-shot paired observations, charged to the existing grant, never admissions."""
    from aeep.hosts.codex_inspection import WorkerInspectionResult

    repo = service.repository
    roles = ('control','treatment')
    definition,requests,workers,probe_definitions = authorize_component(service,control_request,treatment_request,bindings)
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

    facts: list[dict[str,Any]] = [dict(model_turns=0) for _ in roles]
    adapters: list[CodexAppServerAdapter] = []
    journals: list[EventJournal] = []
    canary = 'aeep-synthetic-'+uuid4().hex
    markers = ['control-'+uuid4().hex,'treatment-'+uuid4().hex]
    pending: asyncio.Task[dict[str,Any]] | None = None
    failure: BaseException | None = None
    stage = 'start'
    result: dict[str, Any] = {'pair_definition_digest':content_digest(definition), 'model_turns':0,
                             'component_evidence_only':True,'workers':{}}

    def recheck() -> None:
        for request in requests:
            repo.authorize(request)
            verify_dependencies(request.executable_dependencies)
        for index, binding in enumerate(bindings):
            binding.verify(getattr(definition,roles[index]).managed_host_config().invocation.dynamic_tools_digest,workers[index].digest())

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
            async with asyncio.timeout(120):
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
                        facts[index]['inspection'].pop('full_conformance',None)
                        if not facts[index]['inspection'].get('inspection_complete') or not facts[index]['inspection'].get('identity_digest'):
                            raise ConfigurationError('worker policy inspection incomplete')
                        identity = adapter._worker_process_id
                        if identity is None:
                            raise ConfigurationError('worker process identity unavailable')
                        stage = role+':composed_declaration'
                        declaration = await inspect_dynamic_declaration(adapter, config=config,
                            worker=worker, binding=bindings[index], journal=journals[index], recheck=recheck)
                        facts[index]['dynamic_declaration'] = declaration
                        facts[index]['active_policy'] = declaration['active_policy']
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
                        program = CHECK.replace('PATHS',repr(paths)).replace('DOCX_PROBE','False')
                        for old, new in zip(SKILL_PROFILES['spreadsheets:1'][:3], SKILL_PROFILES[definition.profile][:3], strict=True):
                            program = program.replace(repr(old), repr(new))
                        facts[index]['filesystem'] = filesystem_observation(await observed_command(index,'filesystem',program))
                    for index in range(2):
                        dependencies = await observed_command(index,'dependencies',DEPENDENCY,30000)
                        if dependencies != definition.spreadsheets.dependency_expectations:
                            raise ConfigurationError('shared Spreadsheets dependency probe differs')
                        facts[index]['dependencies'] = dependencies
                        catalog = await adapters[index].inventory()
                        facts[index]['physical_spreadsheets'] = physical_spreadsheets_observation(
                            definition,roles[index],facts[index],catalog)
                    if facts[0]['physical_spreadsheets'] != facts[1]['physical_spreadsheets']:
                        raise ConfigurationError('discovery and AEEP physical Spreadsheets observations differ')
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
            try:
                import aeep.router
                source_root=Path(aeep.router.__file__).resolve().parents[2]
                if verification_source_digest(source_root)!=SOURCE:
                    raise ConfigurationError('final composed worker source changed')
                for request in requests:
                    verify_dependencies(request.executable_dependencies)
                result['source_unchanged']=True
            except Exception as exc:
                failure=exc
                result.update(failed_stage='final_source_drift',error_type=type(exc).__name__,source_unchanged=False)
            for index,(request,operation,worker) in enumerate(zip(requests,operations,workers,strict=True)):
                try:
                    named = composed_observations(definition,roles[index],worker,facts[index],bindings[index])
                    expected = expected_component_probes(definition,roles[index],bindings[index])
                except Exception as exc:
                    named = {}
                    expected = {}
                    facts[index]['component_observation_error_type'] = type(exc).__name__
                    failure = failure or exc
                complete = failure is None and 'cleanup_error_type' not in facts[index] and named==expected
                facts[index]['component_probes_match'] = complete
                facts[index]['component_observations'] = named
                journal = journals[index] if len(journals)>index else None
                evidence_digest = None
                probe_digests = []
                if journal is not None:
                    operation_start = repo.get('operation_start',operation)
                    if operation_start.get('operation_id') != operation:
                        raise ConfigurationError('worker component probe lost its reserved parent operation')
                    charged_operation_digest = content_digest(operation_start)
                    for name,value in named.items():
                        journal.append('artifact.created','probe-'+name,evidence_ref=content_digest(value))
                    journal.append('artifact.created','observations',evidence_ref=content_digest(facts[index]))
                    journal.append('execution.completed' if complete else 'execution.failed','terminal')
                    evidence = journal.evidence(getattr(definition,roles[index]).managed_host_config().adapter_id,
                        RawExecution(status=ExecutionStatus.SUCCESS if complete else ExecutionStatus.FAILED,
                            metadata={'boundary_digest':worker.digest(),'host_runtime_digest':facts[index].get('inspection',{}).get('identity_digest')}))
                    evidence_digest = repo.put('execution_evidence',evidence.digest(),evidence)
                    for name,value in named.items():
                        recorded_probe = BoundaryProbe(schema_version='assessment.boundary-probe.v2',
                            probe_id=new_id('probe'),name=name,
                            implementation_digest=content_digest(probe_definitions[index][name]),
                            worker_digest=worker.digest(),execution_evidence_digest=evidence_digest,
                            observed=value,charged_operation_digest=charged_operation_digest)
                        probe_digests.append(repo.put('boundary_probe',recorded_probe.probe_id,recorded_probe))
                record = WorkerInspectionResult(request_id=request.plan_id,worker_digest=worker.digest(),
                    execution_evidence_digest=evidence_digest,observations=facts[index])
                repo.put('worker_pair_inspection',operation,record)
                repo.finish_operation(operation,elapsed_seconds=time.perf_counter()-reserved[index][1])
                result['workers'][roles[index]] = {'record_digest':content_digest(record),'probe_digests':probe_digests,'component_probes_match':complete}
    result['component_probes_match'] = all(value['component_probes_match'] for value in result['workers'].values())
    if isinstance(failure,(asyncio.CancelledError,KeyboardInterrupt,SystemExit)):
        raise failure
    return result
