"""Controlled protocol fixtures never establish real authenticated conformance."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_v08_assessment import setup_assessment
from test_v08_managed_workers import binding

from aeep.assessment.boundary import BoundaryProbeDefinition, prepare_model_probe
from aeep.assessment.models import AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.hosts import codex_pair_inspection as paired
from aeep.hosts.base import HostModel
from aeep.models import ExecutorSpec

pytestmark = pytest.mark.assessment_lifecycle


def definition(*, task_profile=False):
    workers = [binding(schema_version='execution.worker.v2',permissions_profile='aeep',
        network_id='b'*64,model_proxy_url='http://172.22.0.2:3128',credential_volume='aeep-auth-'+role,
        reviewed_files={'/opt/dependencies/plugin/skills/spreadsheets/SKILL.md':'a'*64} if role=='treatment' else None
    ).model_copy(update={'worker_id':role}) for role in ('control','treatment')]
    specs = [ExecutorSpec(id=worker.worker_id,capability='aeep.conformance.connectivity@1',kind='host_managed',resource_pool='pool',
        description='Controlled paired fixture',config={'adapter_id':'codex-app-server:'+worker.worker_id,
            'argv':[worker.binary,'app-server'],'managed_worker':worker.model_dump(mode='json'),
            'instructions':'No model invocation in the paired probe','timeout_seconds':60}) for worker in workers]
    if task_profile:
        for role,spec in zip(('control','treatment'),specs,strict=True):
            spec.capability = 'assessment.workbook@1'
            spec.config['invocation'] = {'mode':'turn','local_profile':'capable_local'} if role == 'control' else {
                'mode':'skill','local_profile':'capable_local','exposure':'optional','skill_name':'Spreadsheets',
                'skill_path':'/opt/dependencies/plugin/skills/spreadsheets/SKILL.md','skill_sha256':'a'*64}
            spec.config['artifact'] = {'input_field':'workbook_b64','output_field':'workbook_b64',
                'input_name':'input.xlsx','output_name':'output.xlsx','max_bytes':150000}
    return paired.WorkerPairInspection(schema_version='assessment.worker-pair-inspection.v2' if task_profile else 'assessment.worker-pair-inspection.v1',
        control=specs[0],treatment=specs[1],shared_versions={'pandas':'2.3.2','openpyxl':'3.1.5'},
        candidate_skill_digest='a'*64,differential={
            'shared_definition_digest':'c'*64,'control_inventory':{'python':'d'*64},
            'treatment_inventory':{'python':'d'*64,'spreadsheets':'a'*64},'candidate_inventory':{'spreadsheets':'a'*64},
            'candidate_paths':sorted(paired.CANDIDATE_PATHS),'candidate_aliases':['Spreadsheets','spreadsheets:Spreadsheets']})


def prepare(service,plan,definition):
    sources = [prepare_model_probe(service,source_plan_id=plan.plan_id,
        definition=BoundaryProbeDefinition(name='model_connectivity',executor=getattr(definition,role),expected={'connected':True}))
        for role in ('control','treatment')]
    result = paired.prepare_pair(service,*(item.plan_id for item in sources),definition)
    return [ConformanceProbeRequest.model_validate(item) for item in result['requests']]


def approve(service,grant,requests):
    digests = {digest for request in requests for digest in [*request.definition_digests,request.subject_digest]}
    definitions = {digest:json.loads(service.repository.store._connection.execute(
        'SELECT payload_json FROM assessment_records WHERE digest=?',(digest,)).fetchone()[0]) for digest in digests}
    service.repository.approve_bundle(AssessmentScopeAmendment(authorization_id=grant.authorization_id,authorization_digest=content_digest(grant),
        subject_digests=list({r.subject_digest for r in requests}),recipe_digests=list({r.recipe_digest for r in requests}),
        environment_digests=list({r.environment_digest for r in requests}),reviewed_digests=sorted(digests)),definitions)


def mock_workers(monkeypatch, definition, *, fail=None, service=None, requests=None):
    adapters = []
    removed = {role:asyncio.Event() for role in ('control','treatment')}
    candidate_path, _alias, _directory, names = paired.SKILL_PROFILES[definition.profile]
    candidate_name = sorted(names)[0]
    def skills(role):
        target = getattr(definition,role).managed_host_config().invocation
        result = [{'name':item.name,'path':item.path,'enabled':True} for item in target.supporting_skills] if target else []
        if role == 'treatment':
            result.append({'name':candidate_name,'path':candidate_path,'enabled':True})
        if fail=='candidate_in_control' and role=='control':
            result.append({'name':candidate_name,'path':candidate_path,'enabled':True})
        if fail=='background_missing':
            result=[item for item in result if item['name']!='background']
        if fail=='unexpected_skill':
            result.append({'name':'unreviewed','path':'/opt/unreviewed/SKILL.md','enabled':True})
        if fail=='candidate_path' and role=='treatment':
            result[-1]['path']='/opt/unreviewed/SKILL.md'
        return result
    async def collect(adapter,config,journal,recheck):
        recheck()
        if fail=='collection':
            return {'inspection_complete':False}
        if fail=='cancel':
            raise asyncio.CancelledError()
        if fail=='revoked':
            service.repository.review(requests[0].pair_definition_digest,revoke=True)
            recheck()
        return {'inspection_complete':True,'identity_digest':'e'*64,
            'config/read':{key:{'matches':True} for key in ('config/web_search','config/mcp_servers',
                *(f'config/features/{name}' for name in ('apps','memories','multi_agent','browser_use','computer_use')))},
            'configRequirements/read':{'available':False} if fail=='policy' else {str(i):{'matches':True} for i in range(3)},
            'advertised_inventory':{'apps':[],'servers':[],'skills':skills(adapter.role)},
            'sandbox_command':{'workspace_write':True,'proxy':'denied','direct':'denied'}}
    async def cleanup(worker,identity):
        removed[worker.worker_id].set()
        return fail!='cleanup'
    def factory(spec,**kwargs):
        role=spec.id
        async def request(method,params,**kwargs):
            assert method in {'thread/start','command/exec'}
            if method=='thread/start':
                if not definition.schema_version.endswith('.v1'):
                    assert params['permissions']=='aeep' and params['approvalPolicy']=='never'
                    assert params['config']['features.shell_tool'] and params['config']['features.unified_exec']
                    assert sum(s['enabled'] for s in params['config']['skills.config']) == len(skills(role))
                else:
                    assert set(params)=={'ephemeral','cwd','model'}
                return {'activePermissionProfile':{'id':'aeep','extends':None},'approvalPolicy':'never','cwd':'/workspace',
                    'thread':{'id':role},'approvalsReviewer':'user'}
            assert 'permissionProfile' not in params and 'sandboxPolicy' not in params
            program=params['command'][-1]
            if 'time.sleep(60)' in program:
                await removed[role].wait()
                if fail=='incomplete_stream':
                    raise TimeoutError()
                raise paired.CodexProtocolError('controlled transport ended after removal')
            if program==paired.DEPENDENCY:
                value={'authoring_helper':True,'artifact_tool_csv':True}
            else:
                value={'own_workspace':'readable','other_workspace':'absent','credential_canary':'readable' if fail=='canary' else 'denied',
                    'external_answer':'absent','shared_workbook_roundtrip':True,'pandas':'2.3.2','openpyxl':'3.1.5',
                    'candidate_skill_sha256':'a'*64 if role=='treatment' else None,'candidate_alias':role=='treatment','candidate_runtime':role=='treatment'}
            if fail=='malformed':
                value['unexpected']='do-not-persist'
            return {'exitCode':0,'stdout':json.dumps(value)}
        adapter=SimpleNamespace(role=role,_worker_process_id=role,_worker_security=None,
            transport=SimpleNamespace(request=AsyncMock(side_effect=request),close=AsyncMock()),
            list_models=AsyncMock(return_value=[HostModel(id='fixture')]),
            resolve_identity=AsyncMock(return_value=('f' if fail=='identity' else 'e')*64))
        adapters.append(adapter)
        return adapter
    async def docker(worker,*args,**kwargs):
        if fail=='cgroup' and paired.SEED in args:
            return json.dumps({'unexpected':'do-not-persist'})
        if 'inspect' in args:
            return json.dumps({'image':worker.image,'readonly':True,'network':worker.network_id,
                'mounts':[{'Type':'volume','Name':worker.credential_volume,'Destination':'/worker/auth'}]})
        return json.dumps({'cpu.max':'100000 100000','memory.max':'1073741824','pids.max':'64'}) if paired.SEED in args else '{}'
    monkeypatch.setattr(paired,'collect',collect)
    monkeypatch.setattr(paired.CodexAppServerAdapter,'from_executor',factory)
    monkeypatch.setattr(paired,'docker',docker)
    monkeypatch.setattr(paired.ManagedWorkerBinding,'artifact',AsyncMock(return_value={'data':'ready'}))
    monkeypatch.setattr(paired.ManagedWorkerBinding,'cleanup',cleanup)
    if not definition.schema_version.endswith('.v1'):
        from aeep.hosts import codex_invocation
        monkeypatch.setattr(codex_invocation,'inventory',AsyncMock(return_value={'apps':[],'servers':[],
            'skills':skills('treatment')}))
        monkeypatch.setattr(codex_invocation,'verify_thread_inventory',AsyncMock())
    return adapters


@pytest.mark.parametrize('task_profile',[False,True])
async def test_pair_requires_exact_review_budgets_and_retains_canonical_probe_lineage(tmp_path,monkeypatch,task_profile):
    router,service,plan,grant=setup_assessment(tmp_path)
    try:
        value=definition(task_profile=task_profile)
        requests=prepare(service,plan,value)
        assert all(r.schema_version.endswith('.v3') for r in requests)
        adapters=mock_workers(monkeypatch,value)
        with pytest.raises(ConfigurationError,match=r'scope|review'):
            await paired.execute_pair(service,*(r.plan_id for r in requests))
        assert not adapters
        approve(service,grant,requests)
        with pytest.raises(ConfigurationError,match='differs'):
            await paired.execute_pair(service,*(r.plan_id for r in reversed(requests)))
        result=await paired.execute_pair(service,*(r.plan_id for r in requests))
        assert result['probes_match'] and not result['full_conformance'] and result['model_turns']==0
        assert len(adapters)==2
        for role,request in zip(('control','treatment'),requests,strict=True):
            worker=result['workers'][role]
            assert len(worker['probe_digests'])==11
            record=service.repository.get('worker_pair_inspection',worker['record_digest'])
            evidence=ExecutionEvidence.model_validate(service.repository.get('execution_evidence',record['execution_evidence_digest']))
            assert evidence.complete and evidence.cancellation_confirmed and evidence.identity_digest=='e'*64
            assert evidence.boundary_digest==request.worker_digest and evidence.events[-1].kind=='execution.completed'
            for digest in worker['probe_digests']:
                probe=service.repository.get('boundary_probe',digest)
                assert probe['execution_evidence_digest']==record['execution_evidence_digest']
                assert any(event.evidence_ref==content_digest(probe['observed']) for event in evidence.events)
            ledger=service.repository.operation_ledger(request.plan_id)
            assert len(ledger.operations)==1 and ledger.operations[0].reserved.max_model_turns==0
            assert 0 < ledger.operations[0].elapsed_seconds < 240
        with pytest.raises(ConfigurationError,match='blind retry'):
            await paired.execute_pair(service,*(r.plan_id for r in requests))
        assert len(adapters)==2
    finally:
        await router.close()


@pytest.mark.parametrize('failure',['collection','canary','cleanup','revoked','incomplete_stream','cancel','policy','malformed','cgroup','identity'])
async def test_pair_faults_cannot_become_passing_evidence_or_lose_charges(tmp_path,monkeypatch,failure):
    router,service,plan,grant=setup_assessment(tmp_path)
    try:
        value=definition()
        requests=prepare(service,plan,value)
        approve(service,grant,requests)
        adapters=mock_workers(monkeypatch,value,fail=failure,service=service,requests=requests)
        if failure=='cancel':
            with pytest.raises(asyncio.CancelledError):
                await paired.execute_pair(service,*(r.plan_id for r in requests))
        else:
            result=await paired.execute_pair(service,*(r.plan_id for r in requests))
            assert not result['probes_match'] and not result['full_conformance']
        assert adapters and all(adapter.transport.close.await_count==1 for adapter in adapters)
        for request in requests:
            ledger=service.repository.operation_ledger(request.plan_id)
            assert len(ledger.operations)==1 and ledger.operations[0].elapsed_seconds is not None
            record=service.repository.get('worker_pair_inspection','pair-inspection:'+request.plan_id)
            assert not record['observations']['probes_match']
            assert 'do-not-persist' not in json.dumps(record)
    finally:
        await router.close()


async def test_second_reservation_failure_starts_no_worker_and_retains_first_operation(tmp_path,monkeypatch):
    router,service,plan,grant=setup_assessment(tmp_path,operations=1)
    try:
        value=definition()
        requests=prepare(service,plan,value)
        approve(service,grant,requests)
        adapters=mock_workers(monkeypatch,value)
        with pytest.raises(ConfigurationError,match='budget exhausted'):
            await paired.execute_pair(service,*(r.plan_id for r in requests))
        assert not adapters
        ledger=service.repository.operation_ledger(requests[0].plan_id)
        assert len(ledger.operations)==1 and ledger.operations[0].elapsed_seconds is not None
        assert not service.repository.operation_ledger(requests[1].plan_id).operations
    finally:
        await router.close()


@pytest.mark.parametrize('drift',['operation','pair_definition','runtime','worker','missing_probe','probe'])
async def test_pair_authority_rejects_definition_drift_before_any_debit(tmp_path,monkeypatch,drift):
    router,service,plan,grant=setup_assessment(tmp_path)
    try:
        value=definition()
        requests=prepare(service,plan,value)
        approve(service,grant,requests)
        original=service.repository.get
        probe_digest=content_digest(BoundaryProbeDefinition(name='events',executor=value.control,
            expected=paired.expected_probes(value,'control')['events']))
        def get(kind,identity):
            payload=original(kind,identity)
            if kind=='conformance_request' and identity==requests[0].plan_id:
                if drift=='operation':
                    payload.update(schema_version='assessment.conformance-request.v1',operation=None)
                    payload.pop('pair_definition_digest')
                if drift=='runtime':
                    payload['executable_dependencies']={}
                if drift=='worker':
                    payload['worker_digest']='f'*64
                if drift=='missing_probe':
                    payload['definition_digests'].remove(probe_digest)
            if kind=='worker_pair_definition' and drift=='pair_definition':
                payload['shared_versions']['pandas']='changed'
            if kind=='boundary_probe_definition' and identity==probe_digest and drift=='probe':
                payload['expected']={'command_responses_complete':False}
            return payload
        monkeypatch.setattr(service.repository,'get',get)
        with pytest.raises(ConfigurationError):
            paired.authorize_pair(service,*(r.plan_id for r in requests))
        assert not service.repository.operation_ledger(requests[0].plan_id).operations
    finally:
        await router.close()


def test_pair_request_version_cannot_expand_historical_inspection():
    value={'subject_digest':'a'*64,'recipe_digest':'b'*64,'mapping_digest':'c'*64,'environment_digest':'d'*64,
        'authorization_id':'grant','definition_digests':['e'*64],'worker_digest':'f'*64,'executable_dependencies':{}}
    old=ConformanceProbeRequest(**value)
    assert 'operation' not in old.model_dump() and 'pair_definition_digest' not in old.model_dump()
    for updates in ({'schema_version':'assessment.conformance-request.v2','operation':'worker_pair_inspection'},
                    {'schema_version':'assessment.conformance-request.v3','operation':'worker_pair_inspection'},
                    {'schema_version':'assessment.conformance-request.v3','operation':'worker_inspection','pair_definition_digest':'e'*64}):
        with pytest.raises(ValueError,match='paired inspection'):
            ConformanceProbeRequest(**value,**updates)


@pytest.mark.parametrize('change',['paths','versions','entrypoint','credentials','skill_pin'])
def test_pair_profile_refuses_unreviewed_dependencies_and_boundaries(change):
    value=definition().model_dump(mode='json')
    if change=='paths':
        value['differential']['candidate_paths'].append('/worker/auth')
    elif change=='versions':
        value['shared_versions']={}
    elif change=='entrypoint':
        value['control']['config']['argv'].append('--unknown')
    elif change=='credentials':
        value['control']['config']['managed_worker']['credential_volume']=None
    else:
        value['treatment']['config']['managed_worker']['reviewed_files']={}
    with pytest.raises(ValueError):
        paired.WorkerPairInspection.model_validate(value)


def test_probe_observations_do_not_retain_unrelated_metadata():
    worker=paired.binding_from_config(definition().control.managed_host_config().managed_worker)
    result=paired.container_observation({'image':worker.image,'network':worker.network_id,'readonly':True,
        'environment':'do-not-persist','mounts':[{'Type':'volume','Name':worker.credential_volume,
            'Destination':'/worker/auth','Source':'do-not-persist'}]},worker)
    assert 'do-not-persist' not in json.dumps(result)
    with pytest.raises(ConfigurationError):
        paired.container_observation({'mounts':None,'readonly':True},worker)
    with pytest.raises(ConfigurationError):
        paired.filesystem_observation({'unexpected':'do-not-persist'})


@pytest.mark.parametrize('change',['legacy','settings','profile','catalog','candidate'])
def test_task_profile_probe_rejects_unreviewed_differences(change):
    value=definition(task_profile=True).model_dump(mode='json')
    if change=='legacy':
        value['schema_version']='assessment.worker-pair-inspection.v1'
    elif change=='settings':
        value['treatment']['config']['timeout_seconds']=120
    elif change=='profile':
        value['control']['config']['invocation']['local_profile']=None
    elif change=='catalog':
        value['treatment']['config']['invocation']['native_catalog']=True
    else:
        value['treatment']['config']['invocation']['skill_sha256']='f'*64
    with pytest.raises(ValueError):
        paired.WorkerPairInspection.model_validate(value)


def extended_definition(profile, *, native_catalog=False, search=False):
    value = definition(task_profile=True).model_dump(mode='json')
    value.update(schema_version='assessment.worker-pair-inspection.v3', profile=profile)
    skill, alias, directory, names = paired.SKILL_PROFILES[profile]
    value['differential']['candidate_paths'] = [skill,alias,directory]
    value['differential']['candidate_aliases'] = sorted(names)
    for role in ('control','treatment'):
        config = value[role]['config']
        config['managed_worker']['reviewed_files'] = {skill:'a'*64} if role=='treatment' else {}
        target = config['invocation']
        if role=='treatment':
            target.update(skill_name=sorted(names)[0],skill_path=skill)
        if search:
            config.pop('artifact')
            config['input_tree']='local_search_tree:1'
            config['assessment_adapter']={'input_transform':'local_search_tree:2','read_only_roots':['/tmp/fixtures']}
        if native_catalog:
            target.update(native_catalog=True,supporting_skills=[{
                'name':'background','path':'/opt/dependencies/background/SKILL.md','sha256':'9'*64}])
            config['managed_worker']['reviewed_files']['/opt/dependencies/background/SKILL.md']='9'*64
            value['differential'][role+'_inventory']['skill:background']='9'*64
        if not config['managed_worker']['reviewed_files']:
            config['managed_worker']['reviewed_files']=None
    return paired.WorkerPairInspection.model_validate(value)


@pytest.mark.parametrize('profile,native,search',[
    ('spreadsheets:1',True,False), ('ponytail:1',False,False), ('ponytail:1',True,True)])
async def test_reviewed_skill_and_native_catalog_pairs_share_the_existing_probe_path(tmp_path,monkeypatch,profile,native,search):
    router,service,plan,grant=setup_assessment(tmp_path)
    try:
        value=extended_definition(profile,native_catalog=native,search=search)
        requests=prepare(service,plan,value)
        approve(service,grant,requests)
        adapters=mock_workers(monkeypatch,value)
        result=await paired.execute_pair(service,*(request.plan_id for request in requests))
        assert result['probes_match'] and not result['full_conformance']
        calls=[call.args[1]['command'][-1] for adapter in adapters for call in adapter.transport.request.call_args_list
               if call.args[0]=='command/exec']
        assert (paired.DEPENDENCY in calls)==(profile=='spreadsheets:1')
        assert any(paired.SKILL_PROFILES[profile][0] in program for program in calls)
    finally:
        await router.close()


@pytest.mark.parametrize('change',['legacy','background_pin','background_difference','background_candidate','background_inventory','catalog_difference','candidate_path'])
def test_extended_pair_rejects_unreviewed_shared_or_candidate_changes(change):
    value=extended_definition('ponytail:1',native_catalog=True).model_dump(mode='json')
    config=value['control']['config']
    if change=='legacy':
        value['schema_version']='assessment.worker-pair-inspection.v2'
    elif change=='background_pin':
        config['managed_worker']['reviewed_files']=None
    elif change=='background_difference':
        config['invocation']['supporting_skills']=[]
    elif change=='background_candidate':
        for role in ('control','treatment'):
            value[role]['config']['invocation']['supporting_skills'][0]['name']='ponytail'
    elif change=='background_inventory':
        value['differential']['control_inventory'].pop('skill:background')
        value['differential']['treatment_inventory'].pop('skill:background')
    elif change=='catalog_difference':
        config['invocation']['native_catalog']=False
    else:
        value['treatment']['config']['invocation']['skill_path']='/opt/dependencies/ponytail'
    with pytest.raises(ValueError):
        paired.WorkerPairInspection.model_validate(value)


@pytest.mark.parametrize('failure',['candidate_in_control','background_missing','unexpected_skill','candidate_path'])
async def test_extended_inventory_requires_observed_candidate_absence_and_exact_shared_skills(tmp_path,monkeypatch,failure):
    router,service,plan,grant=setup_assessment(tmp_path)
    try:
        value=extended_definition('ponytail:1',native_catalog=True)
        requests=prepare(service,plan,value)
        approve(service,grant,requests)
        mock_workers(monkeypatch,value,fail=failure)
        result=await paired.execute_pair(service,*(request.plan_id for request in requests))
        assert not result['probes_match'] and not result['full_conformance']
        assert all(service.repository.operation_ledger(request.plan_id).operations[0].elapsed_seconds is not None
                   for request in requests)
    finally:
        await router.close()
