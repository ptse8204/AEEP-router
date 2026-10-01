"""Pure reviewed-profile assembly. No repository writes, reservations or hosts.

The caller supplies concrete operator-produced callback definitions and exact
profiles; this function cannot fabricate task scopes or conformance evidence.
"""
import copy
from pathlib import Path
from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import ConformanceProbeRequest, content_digest
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
from aeep.hosts.workers import binding_from_config
from aeep.models import ActionRequest, ExecutorSpec, SideEffect

SOURCE = 'ade3b4e98078a7a33a9a1ff9bf1a917063872dbc4eeba96d42ee33cec554a3d1'
SELECTED_WORKER = '7ceec1d0a3149ad4412c940c6d7dadab84e20576d6032b3ac55c278386bcbc2d'


def assemble(*, pair_document, callback_documents, source_request, action_document,
             executable_dependencies, request_id, source_root):
    from aeep.assessment.verification import verification_source_digest
    if verification_source_digest(Path(source_root)) != SOURCE:
        raise ValueError('current source differs from reviewed assembly source')
    pair = ComposedPairDefinition.model_validate(pair_document)
    callbacks = {}
    for spec in (pair.control, pair.treatment):
        config = spec.managed_host_config()
        worker = binding_from_config(config.managed_worker)
        assert worker is not None and config.invocation is not None
        digest = pair.callback_bindings[worker.digest()]
        document = callback_documents[digest]
        identity = document['identity']
        if (content_digest(document) != digest or document['max_calls'] != 1
                or identity['approval_ceiling'] != 'read'
                or identity.get('scope_limits') != {'max_attempts': 1, 'max_attempt_seconds': 10.0}
                or identity['worker_digest'] != worker.digest()
                or identity['native_backend_digest'] != pair.native_backends[worker.digest()]
                or identity['implementation_digest'] != CodexDynamicTools.implementation_digest()
                or config.approval_ceiling != SideEffect.READ):
            raise ValueError('concrete one-call READ callback profile differs')
        callbacks[digest] = document
    selected = [spec for spec in (pair.control, pair.treatment)
                if binding_from_config(spec.managed_host_config().managed_worker).digest() == SELECTED_WORKER]
    if len(selected) != 1:
        raise ValueError('refreshed worker must select one exact composed profile')
    spec = selected[0]
    action = ActionRequest.model_validate(action_document)
    if (action.capability != spec.capability or action.constraints.allowed_executor_ids != [spec.id]
            or not spec.idempotent or spec.side_effect != SideEffect.READ
            or spec.estimate.cash.upper_bound_usd != 0):
        raise ValueError('fixed one-attempt READ action differs')
    own_path = Path(__file__).resolve()
    if executable_dependencies.get(str(own_path)) != file_digest(own_path):
        raise ValueError('assembly executable is not pinned')
    verify_dependencies(executable_dependencies)
    definition = BoundaryProbeDefinition(name='callback_authority', executor=spec,
        expected={'callback_origin': 'native_app_server', 'native_callback_observed': True})
    pair_digest = content_digest(pair)
    request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v4',
        plan_id=request_id, subject_digest=source_request['subject_digest'],
        recipe_digest=source_request['recipe_digest'], mapping_digest=source_request['mapping_digest'],
        environment_digest=source_request['environment_digest'], authorization_id=source_request['authorization_id'],
        definition_digests=list(dict.fromkeys([*source_request['definition_digests'], pair_digest,
            *callbacks, content_digest(definition), content_digest(action)])),
        worker_digest=SELECTED_WORKER, executable_dependencies=executable_dependencies,
        operation='composed_pair_inspection', pair_definition_digest=pair_digest, composed_model_turns=1)
    return {'source_digest': SOURCE, 'pair': pair.model_dump(mode='json'),
        'pair_digest': pair_digest, 'callbacks': callbacks,
        'definition': definition.model_dump(mode='json'), 'definition_digest': content_digest(definition),
        'action': action.model_dump(mode='json'), 'action_digest': content_digest(action),
        'request': request.model_dump(mode='json'), 'request_digest': content_digest(request),
        'execution_authorized': False, 'full_conformance': False}


def profiles_from_existing(*, existing_pair, callback_documents_by_role, treatment_tool):
    """Retain immutable worker/config facts; declare only the actual callback delta.

    Historical image/skill differences remain in the differential. This is a
    boundary probe pair, not evidence of equal discovery access for value trials.
    """
    from aeep.hosts.codex_invocation import contract_digest
    specs = {}
    bindings = {}
    backends = {}
    for role in ('control', 'treatment'):
        value = copy.deepcopy(existing_pair[role])
        config = value['config']
        old = config['invocation']
        invocation = {key: old[key] for key in ('supporting_tools', 'supporting_skills',
            'native_catalog', 'local_profile') if key in old}
        document = callback_documents_by_role[role]
        digest = content_digest(document)
        worker = binding_from_config(config['managed_worker'])
        if document['identity']['worker_digest'] != worker.digest():
            raise ValueError('callback document is not for selected immutable worker')
        invocation.update(mode='turn' if role == 'control' else 'dynamic_tool',
                          dynamic_tools_digest=digest, local_profile='capable_local')
        if role == 'treatment':
            declarations = [item for item in document['tools'] if item['name'] == treatment_tool]
            if len(declarations) != 1:
                raise ValueError('exact reviewed treatment declaration required')
            invocation.update(server=document['namespace'], tool=treatment_tool,
                tool_sha256=contract_digest(declarations[0]), exposure='required')
        config['instructions'] = ('Call the available operator-bound workbook task tool exactly once with {}. '
            'The fixed artifact wrapper supplies input.xlsx and writes output.xlsx. Do not use shell tools, '
            'read or emit base64, or repeat the call. Input task contract: {input} Return only {"completed": true} '
            'after the callback reports success.')
        config['invocation'] = invocation
        config['adapter_options']['experimental_api'] = True
        specs[role] = ExecutorSpec.model_validate(value)
        bindings[worker.digest()] = digest
        backends[worker.digest()] = document['identity']['native_backend_digest']
    return ComposedPairDefinition(control=specs['control'], treatment=specs['treatment'],
        differential=existing_pair['differential'], shared_versions=existing_pair['shared_versions'],
        callback_bindings=bindings, native_backends=backends).model_dump(mode='json')
