"""Finite composed-worker observations; no native callback or full-conformance claim.

Literal adaptation of existing execute_pair: the only runtime change is the
composed declaration hook, v4 authorization and120s body. Existing synthetic
commands, canary removal, interruption witness, cleanup, journal and accounting
are retained. Inherited physical candidate differences are measured separately
and remain a value-comparison confounder.
"""
from typing import Literal
from aeep.hosts.codex_pair_inspection import *
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.models import StrictModel
from aeep.assessment.identity import file_digest, runtime_dependencies
from aeep.assessment.verification import verification_source_digest
SOURCE="ade3b4e98078a7a33a9a1ff9bf1a917063872dbc4eeba96d42ee33cec554a3d1"

class WorkerComponentDefinition(StrictModel):
    schema_version: Literal['assessment.composed-worker-component.v1'] = 'assessment.composed-worker-component.v1'
    composed: ComposedPairDefinition
    physical_inventory_definition: WorkerPairInspection

    @property
    def control(self): return self.composed.control
    @property
    def treatment(self): return self.composed.treatment
    @property
    def differential(self): return self.composed.differential
    @property
    def shared_versions(self): return self.composed.shared_versions
    @property
    def profile(self): return self.physical_inventory_definition.profile
    @property
    def candidate_skill_digest(self): return self.physical_inventory_definition.candidate_skill_digest


def authorize_component(service, control_request, treatment_request, bindings):
    import aeep.router
    root=Path(aeep.router.__file__).resolve().parents[2]
    if verification_source_digest(root)!=SOURCE:raise ConfigurationError("renew current-source component review")
    repo=service.repository
    requests=[ConformanceProbeRequest.model_validate(repo.get('conformance_request',i)) for i in (control_request,treatment_request)]
    if (len(bindings)!=2 or any(not isinstance(b,CodexDynamicTools) for b in bindings)
            or any(r.operation!='composed_pair_inspection' or r.composed_model_turns!=0 for r in requests)
            or requests[0].pair_definition_digest!=requests[1].pair_definition_digest
            or requests[0].authorization_id!=requests[1].authorization_id):
        raise ConfigurationError('two exact zero-turn composed requests required')
    definitions=[];workers=[];component=None
    for index,(role,request) in enumerate(zip(('control','treatment'),requests,strict=True)):
        grant=repo.authorize(request);verify_dependencies(request.executable_dependencies)
        required=runtime_dependencies();required[str(Path(__file__).resolve())]=file_digest(Path(__file__).resolve())
        if any(request.executable_dependencies.get(k)!=v for k,v in required.items()):raise ConfigurationError('component executable identity missing/changed')
        mapping=BoundaryProbeDefinition.model_validate(repo.get('boundary_probe_definition',request.mapping_digest))
        digest=mapping.expected.get('component_digest')
        current=WorkerComponentDefinition.model_validate(repo.get('composed_worker_component',digest))
        if (content_digest(current)!=digest or digest not in request.definition_digests
                or current.composed!=ComposedPairDefinition.model_validate(repo.get('composed_pair_definition',request.pair_definition_digest))):
            raise ConfigurationError('component/composed definition differs')
        if component is not None and component!=current:raise ConfigurationError('paired component differs')
        component=current
        spec=getattr(current,role);worker=binding_from_config(spec.managed_host_config().managed_worker)
        old_worker=binding_from_config(getattr(current.physical_inventory_definition,role).managed_host_config().managed_worker)
        if (worker is None or old_worker is None or worker!=old_worker
                or current.differential!=current.physical_inventory_definition.differential
                or current.shared_versions!=current.physical_inventory_definition.shared_versions
                or worker.digest()!=request.worker_digest or mapping.executor!=spec
                or mapping.name!='worker_pair_inspection' or content_digest(mapping)!=request.mapping_digest):
            raise ConfigurationError('actual selected worker/component mapping differs')
        binding=bindings[index];document=repo.get('codex_dynamic_tools',binding.digest)
        if (document!=binding.definition() or binding.digest!=current.composed.callback_bindings[worker.digest()]
                or binding.identity['native_backend_digest']!=current.composed.native_backends[worker.digest()]):
            raise ConfigurationError('actual callback declaration differs')
        with repo.store._lock:
            for required in (digest,request.pair_definition_digest,binding.digest):
                review=repo.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',(required,)).fetchone()
                if review is None or review[0]:raise ConfigurationError('component definition review absent/revoked')
        binding.verify(binding.digest,worker.digest())
        require_destination(spec,AssessmentEnvironment.model_validate(repo.get('environment',request.environment_digest)),grant)
        probes={}
        for name,expected in expected_probes(current.physical_inventory_definition,role).items():
            probe=BoundaryProbeDefinition(name=name,executor=spec,expected=expected)
            if (content_digest(probe) not in request.definition_digests
                    or repo.get('boundary_probe_definition',content_digest(probe))!=probe.model_dump(mode='json')):
                raise ConfigurationError('exact worker probe definition not reviewed')
            probes[name]=probe
        definitions.append(probes);workers.append(worker)
    return component,requests,workers,definitions


def composed_observations(definition,role,worker,facts,binding):
    named=observations(definition.physical_inventory_definition,role,worker,facts)
    declaration=facts['dynamic_declaration']
    # ACK attests accepted declarations only; model exposure/use remains unknown.
    if (declaration.get('declaration_acknowledged') is not True
            or declaration.get('binding_digest')!=binding.digest
            or declaration.get('model_turns')!=0 or declaration.get('task_calls')!=0):
        named['candidate_access']['candidate_available']='inconsistent'
    return named

async def execute_composed_workers(service: AssessmentService, control_request: str, treatment_request: str, *, bindings: tuple[CodexDynamicTools, CodexDynamicTools]) -> dict[str, Any]:
    """One-shot paired observations, charged to the existing grant, never admissions."""
    from aeep.hosts.codex_app_server import _select_model_config
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
                except (KeyError,TypeError,ValueError,ZeroDivisionError):
                    named = {}
                complete = failure is None and 'cleanup_error_type' not in facts[index] and named==expected_probes(definition.physical_inventory_definition,roles[index])
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
