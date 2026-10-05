"""Deterministic, bounded configuration search; no task executors or model calls."""
from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from .assessment.models import content_digest
from .assessment.repository import AssessmentRepository
from .economic.prepared import executor_fingerprint
from .errors import AEEPError, ConfigurationError
from .estimator import action_features
from .models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    DataSensitivity,
    ExecutorKind,
    ResourceVector,
)
from .policy import merge_constraints
from .scoring import score_candidate
from .stack_models import (
    ArtifactContract,
    CompatibilityEdge,
    GoalSpec,
    StackComponent,
    StackPlanningConfig,
    StackPortMapping,
    StackPreflight,
    StackProposal,
    TaskNode,
)

if TYPE_CHECKING:
    from .provider_setup import ProviderSetupService
    from .router import Router


def schema_compatibility(producer: dict[str, Any] | None,
                         consumer: dict[str, Any] | None) -> tuple[Literal['compatible', 'incompatible', 'unknown'], list[str]]:
    """Prove a conservative subset relation; never mistake examples for proof."""
    if consumer == {}:
        return 'compatible', []
    if producer is None or consumer is None:
        return 'unknown', ['value schema unavailable']
    supported = {'type', 'properties', 'required', 'additionalProperties', 'items',
                 'enum', 'minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems'}
    def supported_schema(schema: Any) -> bool:
        if not isinstance(schema, dict) or set(schema) - supported:
            return False
        if 'additionalProperties' in schema and not isinstance(schema['additionalProperties'], bool):
            return False
        return (all(supported_schema(child) for child in schema.get('properties', {}).values()) and
                ('items' not in schema or supported_schema(schema['items'])))
    if not supported_schema(producer) or not supported_schema(consumer):
        return 'unknown', ['unsupported schema relationship']
    if producer == consumer:
        return 'compatible', []
    pt, ct = producer.get('type'), consumer.get('type')
    if pt is None or ct is None or not isinstance(pt, str) or not isinstance(ct, str):
        return 'unknown', ['schema type unavailable']
    if pt != ct and (pt, ct) != ('integer', 'number'):
        return 'incompatible', ['schema types differ']
    if 'enum' in consumer and ('enum' not in producer or
            any(value not in consumer['enum'] for value in producer['enum'])):
        return 'unknown', ['output enumeration is not bounded by input enumeration']
    for key in ('minimum', 'minLength', 'minItems'):
        if key in consumer and (key not in producer or producer[key] < consumer[key]):
            return 'unknown', [f'output does not guarantee {key}']
    for key in ('maximum', 'maxLength', 'maxItems'):
        if key in consumer and (key not in producer or producer[key] > consumer[key]):
            return 'unknown', [f'output does not guarantee {key}']
    if ct == 'object':
        pp, cp = producer.get('properties', {}), consumer.get('properties', {})
        if not set(consumer.get('required', [])) <= set(producer.get('required', [])):
            return 'unknown', ['required input properties are not guaranteed']
        if consumer.get('additionalProperties') is False and (
                producer.get('additionalProperties') is not False or not set(pp) <= set(cp)):
            return 'unknown', ['additional output properties may be rejected']
        if set(cp) - set(pp) and producer.get('additionalProperties') is not False:
            return 'unknown', ['unconstrained output property may violate input schema']
        for key in set(pp) & set(cp):
            verdict, reasons = schema_compatibility(pp[key], cp[key])
            if verdict != 'compatible':
                return verdict, reasons
    if ct == 'array':
        return schema_compatibility(producer.get('items'), consumer.get('items'))
    return 'compatible', []


def compatible(producer: ArtifactContract | None,
               consumer: ArtifactContract | None) -> tuple[Literal['compatible', 'incompatible', 'unknown'], list[str]]:
    if producer is None or consumer is None:
        return 'unknown', ['artifact contract unavailable']
    if producer.semantic_type != consumer.semantic_type:
        return 'incompatible', ['semantic types differ']
    unknowns = []
    for field in ('media_type', 'encoding', 'locality', 'confidentiality'):
        expected, actual = getattr(consumer, field), getattr(producer, field)
        if expected is not None:
            if actual is None:
                unknowns.append(f'{field} unavailable')
            elif actual != expected:
                return 'incompatible', [f'{field} differs']
    for field in ('max_bytes', 'max_width', 'max_height', 'max_duration_seconds'):
        maximum, actual = getattr(consumer, field), getattr(producer, field)
        if maximum is not None:
            if actual is None:
                unknowns.append(f'{field} unavailable')
            elif actual > maximum:
                return 'incompatible', [f'{field} exceeds input bound']
    verdict, reasons = schema_compatibility(producer.value_schema, consumer.value_schema)
    if verdict == 'incompatible':
        return verdict, reasons
    unknowns.extend(reasons)
    return ('unknown', unknowns) if unknowns else ('compatible', [])


def port_mapping(router: Router, executor_id: str) -> StackPortMapping:
    return StackPortMapping.model_validate(router.registry.get(executor_id).config.get('stack', {}))


def node_context(node: TaskNode) -> ActionContext:
    classifications = {contract.confidentiality for contract in node.inputs.values()}
    sensitivity = (DataSensitivity.RESTRICTED if 'restricted' in classifications else
                   DataSensitivity.CONFIDENTIAL if 'private' in classifications else DataSensitivity.PUBLIC)
    return ActionContext(data_sensitivity=sensitivity)


def manifest_digest(router: Router) -> str:
    return content_digest(router.manifest)


def proposal_identity(value: StackProposal) -> str:
    return 'stack_' + content_digest(value.model_dump(mode='json', exclude={'proposal_id'}))


def _aggregate(components: list[StackComponent], retries: int) -> tuple[ResourceVector, Decimal | None, Decimal | None]:
    factor = 1 + retries
    fields = ResourceVector.model_fields
    values = {key: sum(getattr(c.estimated, key) for c in components) * factor for key in fields}
    # Serial execution: peak memory is a maximum, consumable dimensions sum.
    values['peak_memory_mb'] = max((c.estimated.peak_memory_mb for c in components), default=0)
    cash = [c.expected_cash_usd for c in components]
    maxima = [c.maximum_cash_usd for c in components]
    return (ResourceVector.model_validate(values),
            sum((v for v in cash if v is not None), Decimal(0)) * factor if all(v is not None for v in cash) else None,
            sum((v for v in maxima if v is not None), Decimal(0)) * factor if all(v is not None for v in maxima) else None)


class StackService:
    def __init__(self, router: Router, *, config: StackPlanningConfig | None = None,
                 setup_service: ProviderSetupService | None = None) -> None:
        self.router = router
        self.config = config or StackPlanningConfig()
        self.repository = AssessmentRepository(router.store)
        self.setup_service = setup_service

    def inspect(self, identity: str) -> StackProposal:
        proposal = StackProposal.model_validate(self.repository.get('stack_proposal', identity))
        if proposal.proposal_id != proposal_identity(proposal):
            raise ConfigurationError('stack proposal identity mismatch')
        return proposal

    def _candidates(self, goal: GoalSpec, node: TaskNode, *, deadline: float | None = None) -> tuple[list[StackComponent], list[str]]:
        action = ActionRequest(capability=node.capability, policy=goal.policy, constraints=goal.constraints, context=node_context(node))
        policy = self.router._policy_for(action)
        found: list[StackComponent] = []
        rejected = []
        for spec in sorted(self.router.registry.find(node.capability), key=lambda item: item.id):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError
            try:
                self.router._require_active_spec(spec)
                ports = port_mapping(self.router, spec.id)
                if node.verification_required and spec.output_schema is None:
                    raise ConfigurationError('required output verification unavailable')
                for name, contract in node.inputs.items():
                    verdict, _ = compatible(contract, ports.inputs.get(name))
                    if verdict != 'compatible':
                        raise ConfigurationError('input contract unresolved')
                for name, contract in node.outputs.items():
                    verdict, _ = compatible(ports.outputs.get(name), contract)
                    if verdict != 'compatible':
                        raise ConfigurationError('output contract unresolved')
                estimate = self.router.estimator.estimate(spec, policy, action_features({}))
                scored = score_candidate(spec, estimate, policy, action.context,
                                         self.router._subscription_quota(spec, action.context))
                if not scored.feasible or scored.score is None:
                    rejected.append(f'{node.node_id}/{spec.id}: policy-ineligible')
                    continue
                with self.router.store._lock:
                    admitted = self.router.store._connection.execute(
                        'SELECT admission_id FROM assessment_admissions WHERE executor_id=? AND revoked=0', (spec.id,)).fetchone()
                found.append(StackComponent(node_id=node.node_id, executor_id=spec.id,
                    executor_fingerprint=executor_fingerprint(spec), ports_digest=content_digest(ports), side_effect=spec.side_effect, idempotent=spec.idempotent, score=scored.score.total,
                    no_additional_capability=spec.kind in {ExecutorKind.HOST, ExecutorKind.DELEGATE},
                    estimated=estimate.resources, expected_cash_usd=estimate.cash.amount_usd,
                    maximum_cash_usd=estimate.cash.upper_bound_usd, setup_ids=ports.setup_ids,
                    evidence_basis='admitted' if admitted else 'configured',
                    evidence_refs=[admitted[0]] if admitted else []))
            except (AEEPError, ValueError, TypeError):
                rejected.append(f'{node.node_id}/{spec.id}: contract, evidence or authority unavailable')
        found.sort(key=lambda item: (item.score, item.executor_id))
        return found, rejected

    @staticmethod
    def _fits(goal: GoalSpec, configuration: list[StackComponent]) -> bool:
        resources, _, maximum = _aggregate(configuration, goal.limits.retry_reserve)
        if maximum is None or maximum > goal.limits.max_cash_usd:
            return False
        constraints = goal.constraints
        if constraints.max_cost_usd is not None and maximum > Decimal(str(constraints.max_cost_usd)):
            return False
        if len(configuration) * (1 + goal.limits.retry_reserve) > goal.limits.max_attempts:
            return False
        if len(configuration) > 64 or len({c.executor_id for c in configuration}) > 32:
            return False
        if resources.latency_ms > goal.limits.max_elapsed_seconds * 1000:
            return False
        checks = [('max_latency_ms', 'latency_ms'), ('max_cpu_ms', 'cpu_ms'),
                  ('max_memory_mb_seconds', 'memory_mb_seconds'), ('max_gpu_ms', 'gpu_ms'),
                  ('max_network_bytes', 'network_bytes'), ('max_peak_memory_mb', 'peak_memory_mb')]
        if any(getattr(constraints, bound) is not None and getattr(resources, field) >
               getattr(constraints, bound) for bound, field in checks):
            return False
        return constraints.max_context_tokens is None or (
            resources.context_tokens + resources.input_tokens + resources.output_tokens <= constraints.max_context_tokens)

    def _edges(self, node: TaskNode, candidate: StackComponent, chosen: list[StackComponent],
               goal: GoalSpec, *, deadline: float, work: list[int]) -> tuple[list[tuple[list[CompatibilityEdge], list[StackComponent]]], bool]:
        by_node = {c.node_id: c for c in chosen}
        inputs = port_mapping(self.router, candidate.executor_id).inputs
        variants: list[tuple[list[CompatibilityEdge], list[StackComponent]]] = [([], [])]
        complete = True
        for binding in node.bindings:
            source = by_node[binding.source_node]
            output = port_mapping(self.router, source.executor_id).outputs.get(binding.source_port)
            target = inputs.get(binding.target_port)
            verdict, reasons = compatible(output, target)
            edge = CompatibilityEdge(source_node=binding.source_node, source_port=binding.source_port,
                target_node=node.node_id, target_port=binding.target_port, verdict=verdict, reasons=reasons)
            options: list[StackComponent] = []
            if verdict != 'compatible':
                for executor_id in sorted(set(self.config.converter_ids)):
                    if not self.router.registry.contains(executor_id):
                        continue
                    spec = self.router.registry.get(executor_id)
                    mapping = port_mapping(self.router, executor_id)
                    if len(mapping.inputs) != 1 or len(mapping.outputs) != 1:
                        continue
                    if compatible(output, next(iter(mapping.inputs.values())))[0] != 'compatible' or compatible(
                            next(iter(mapping.outputs.values())), target)[0] != 'compatible':
                        continue
                    converter_node = TaskNode(node_id=f'convert:{node.node_id}:{binding.target_port}',
                        capability=spec.capability, inputs=mapping.inputs, outputs=mapping.outputs)
                    possible, _ = self._candidates(goal, converter_node, deadline=deadline)
                    options.extend(c for c in possible if c.executor_id == executor_id)
                options.sort(key=lambda c: (c.score, c.executor_id))
                complete &= len(options) <= self.config.candidates_per_node
                options = options[:self.config.candidates_per_node]
            choices: list[StackComponent | None] = list(options) if options else [None]
            expanded: list[tuple[list[CompatibilityEdge], list[StackComponent]]] = []
            for edges, converters in variants:
                for converter in choices:
                    if work[0] >= self.config.max_expansions or time.monotonic() >= deadline:
                        raise TimeoutError
                    work[0] += 1
                    current = edge.model_copy(deep=True)
                    added = [*converters]
                    if converter is not None:
                        added.append(converter)
                        current.verdict, current.reasons = 'compatible', ['reviewed converter required']
                        current.converter_id, current.converter_node = converter.executor_id, converter.node_id
                    if self._fits(goal, [*chosen, *added, candidate]):
                        expanded.append(([*edges, current], added))
            expanded.sort(key=lambda pair: (sum(c.score for c in pair[1]), tuple(c.executor_id for c in pair[1])))
            complete &= len(expanded) <= self.config.beam_width
            variants = expanded[:self.config.beam_width]
        return variants, complete

    def propose(self, goal: GoalSpec, *, parent_id: str | None = None) -> StackProposal:
        if parent_id:
            self.inspect(parent_id)
        goal = GoalSpec.model_validate(goal.model_dump())
        aliases = {'cost': 'cheapest', 'speed': 'fastest', 'quality': 'reliable', 'privacy': 'resource_saver'}
        if goal.policy == 'privacy':
            goal.constraints = merge_constraints(goal.constraints, ActionConstraints(require_local=True, allow_network=False))
        if goal.policy not in self.router.manifest.policies:
            goal.policy = aliases.get(goal.policy, goal.policy)
        if len(goal.model_dump_json().encode()) > self.config.max_goal_bytes:
            raise ConfigurationError('semantic graph exceeds operator size ceiling')
        started = time.monotonic()
        # Beam entries carry their whole configuration, including conversion cost.
        beam: list[tuple[list[StackComponent], list[CompatibilityEdge]]] = [([], [])]
        rejected: list[str] = []
        alternatives: dict[str, list[str]] = {}
        complete, work = True, [0]
        try:
            for node in goal.ordered_nodes():
                candidates, reasons = self._candidates(goal, node, deadline=started + self.config.max_seconds)
                rejected.extend(reasons)
                alternatives[node.node_id] = [c.executor_id for c in candidates[:self.config.candidates_per_node]]
                complete &= len(candidates) <= self.config.candidates_per_node
                candidates = candidates[:self.config.candidates_per_node]
                next_beam = []
                for chosen, edges in beam:
                    for candidate in candidates:
                        if work[0] >= self.config.max_expansions or time.monotonic() - started > self.config.max_seconds:
                            complete = False
                            break
                        work[0] += 1
                        variants, edge_complete = self._edges(node, candidate, chosen, goal,
                            deadline=started + self.config.max_seconds, work=work)
                        complete &= edge_complete
                        for added_edges, converters in variants:
                            if any(edge.verdict != 'compatible' for edge in added_edges):
                                rejected.extend(f'{e.source_node}->{e.target_node}/{e.target_port}: {e.verdict}: {reason}'
                                                for e in added_edges for reason in e.reasons if e.verdict != 'compatible')
                                continue
                            configuration = [*chosen, *converters, candidate]
                            if self._fits(goal, configuration):
                                next_beam.append((configuration, [*edges, *added_edges]))
                next_beam.sort(key=lambda pair: (sum(c.score for c in pair[0]), tuple(c.executor_id for c in pair[0])))
                complete &= len(next_beam) <= self.config.beam_width
                beam = next_beam[:self.config.beam_width]
                if not beam:
                    break
        except TimeoutError:
            complete, beam = False, []
            rejected.append('Planning allowance exhausted; search incomplete.')
        components, edges = beam[0] if beam else ([], [])
        resources, expected, maximum = _aggregate(components, goal.limits.retry_reserve)
        setup = any(c.setup_ids for c in components)
        proposal = StackProposal(proposal_id='', goal_digest=content_digest(goal), goal=goal,
            manifest_digest=manifest_digest(self.router), components=components, edges=edges,
            estimated=resources, expected_cash_usd=expected if components else None,
            maximum_cash_usd=maximum if components else None,
            status='NEEDS_SETUP' if setup else 'READY' if beam else 'BLOCKED',
            blockers=[] if beam else ['No compatible configuration within the inspected candidates and budget.'],
            warnings=[*rejected, *(['Search was bounded; optimality or global infeasibility is not established.'] if not complete else []),
                      'Resource estimates are priors for unresolved inputs; dispatch revalidates real inputs.'],
            alternatives=alternatives, search_complete=complete, expansions=work[0], parent_id=parent_id)
        proposal.proposal_id = proposal_identity(proposal)
        self.repository.put('stack_proposal', proposal.proposal_id, proposal)
        return proposal

    def optimize(self, identity: str, policy: str) -> StackProposal:
        previous = self.inspect(identity)
        goal = previous.goal.model_copy(update={'policy': policy}, deep=True)
        return self.propose(goal, parent_id=previous.proposal_id)

    def preflight(self, identity: str, *, task_profile: str | None = None) -> StackPreflight:
        proposal = self.inspect(identity)
        blockers = list(proposal.blockers)
        if proposal.goal.propose_only:
            blockers.append('Goal is propose-only; an executable successor requires review.')
        if proposal.maximum_cash_usd != 0 or self.router.manifest.economic_evidence.enabled:
            blockers.append('First-release stack execution requires confirmed-free ordinary execution.')
        setup_requirements: dict[str, dict[str, Any]] = {}
        if manifest_digest(self.router) != proposal.manifest_digest:
            blockers.append('Manifest or policy changed; create a successor proposal.')
        for component in proposal.components:
            try:
                spec = self.router.registry.get(component.executor_id)
                if spec.kind in {ExecutorKind.HTTP, ExecutorKind.MCP, ExecutorKind.MANAGED_HOST}:
                    blockers.append(f'{component.node_id}: remote production execution requires a supported scoped adapter')
                if (executor_fingerprint(spec) != component.executor_fingerprint or
                        content_digest(port_mapping(self.router, spec.id)) != component.ports_digest):
                    raise ConfigurationError('drift')
                self.router._require_active_spec(spec)
            except (AEEPError, ValueError):
                blockers.append(f'{component.node_id}: current executor or admission unavailable')
            if component.setup_ids:
                from .provider_setup import ProviderSetupService
                setup = self.setup_service or ProviderSetupService(self.router.store)
                for setup_id in component.setup_ids:
                    try:
                        setup_requirements[setup_id] = setup.inspect(setup_id)
                    except ConfigurationError:
                        setup_requirements[setup_id] = {'setup_id': setup_id, 'ready': False, 'handoff': 'Operator setup definition required.'}
                    if not setup.ready(setup_id):
                        blockers.append(f'{component.node_id}: setup {setup_id} requires a current successful check')
        digest = content_digest(proposal)
        covered = False
        with self.router.store._lock:
            review = self.router.store._connection.execute(
                'SELECT revoked FROM assessment_reviews WHERE digest=?', (digest,)).fetchone()
        if self.router._task_activation_digest is not None:
            from .models import TaskScope
            from .profiles import load
            from .tasks import require_activation
            try:
                activation = require_activation(self.router, self.router._task_activation_digest)
                if activation.capability_profile_digest:
                    profile = load(self.router, activation.capability_profile_digest)
                    scope = TaskScope.model_validate(self.repository.get('task_scope', activation.scope_digest))
                    covered = profile.stack_execution and all(
                        scope.executor_fingerprints.get(c.executor_id) == c.executor_fingerprint
                        for c in proposal.components)
            except (AEEPError, ValueError):
                blockers.append('Active task authority is unavailable.')
        if task_profile is not None:
            from .models import TaskScope
            from .profiles import load, preflight
            try:
                profile = load(self.router, task_profile)
                profile_check = preflight(self.router, profile)
                scope = TaskScope.model_validate(self.repository.get('task_scope', profile.scope_digest))
                if not profile_check['ready']:
                    blockers.extend(profile_check['blockers'])
                else:
                    covered = profile.stack_execution and all(
                        scope.executor_fingerprints.get(c.executor_id) == c.executor_fingerprint
                        for c in proposal.components)
                    if not covered:
                        blockers.append('Task profile does not cover this stack configuration.')
            except (AEEPError, ValueError):
                blockers.append('Requested task profile is unavailable.')
        if review is not None and review[0]:
            blockers.append('Exact stack proposal review has been revoked.')
        elif review is None and not covered:
            blockers.append('Exact stack proposal requires operator review before assembly or execution.')
        return StackPreflight(proposal_id=proposal.proposal_id, proposal_digest=digest,
            ready=not blockers, blockers=blockers, warnings=proposal.warnings,
            setup_requirements=list(setup_requirements.values()),
            scope_requirements={'authority_basis': 'active reviewed task profile' if covered else 'exact proposal review plus per-action ceiling',
                'executor_fingerprints': {c.executor_id: c.executor_fingerprint for c in proposal.components},
                'max_attempts': proposal.goal.limits.max_attempts,
                'max_attempt_seconds': proposal.goal.limits.max_attempt_seconds,
                'approval_ceiling': proposal.goal.constraints.max_side_effect.value,
                'task_scope_support': 'native sandbox commands only; other executors retain ordinary per-action authority'})

    def compile(self, identity: str, inputs: dict[str, dict[str, Any]]) -> Any:
        """Materialize a transient workflow. This operation grants no authority."""
        from .models import ActionRequest
        from .workflow import (
            WorkflowBudget,
            WorkflowInputBinding,
            WorkflowOutputProjection,
            WorkflowRequest,
            WorkflowStep,
        )
        proposal = self.inspect(identity)
        selected = {component.node_id: component for component in proposal.components}
        if not selected:
            raise ConfigurationError('blocked stack cannot compile')
        steps = []
        for node in proposal.goal.ordered_nodes():
            if node.node_id not in selected:
                raise ConfigurationError('incomplete stack')
            bindings = []
            dependencies = set(node.depends_on)
            for edge in (edge for edge in proposal.edges if edge.target_node == node.node_id):
                source_node, source_port = edge.source_node, edge.source_port
                if edge.converter_node and edge.converter_id:
                    mapping = port_mapping(self.router, edge.converter_id)
                    input_port, output_port = next(iter(mapping.inputs)), next(iter(mapping.outputs))
                    converter = selected[edge.converter_node]
                    constraints = merge_constraints(proposal.goal.constraints,
                        proposal.goal.constraints.model_copy(update={'allowed_executor_ids': [converter.executor_id]}))
                    steps.append(WorkflowStep(step_id=edge.converter_node,
                        action=ActionRequest(capability=self.router.registry.get(edge.converter_id).capability,
                            input={input_port: None}, policy=proposal.goal.policy, constraints=constraints,
                            context=node_context(TaskNode(node_id=edge.converter_node,
                                capability=self.router.registry.get(edge.converter_id).capability, inputs=mapping.inputs))),
                        depends_on=[source_node], bindings=[WorkflowInputBinding(target_path='/' + input_port,
                            source_step_id=source_node, source_path='/' + source_port)]))
                    source_node, source_port = edge.converter_node, output_port
                dependencies.add(source_node)
                bindings.append(WorkflowInputBinding(target_path='/' + edge.target_port,
                    source_step_id=source_node, source_path='/' + source_port))
            values = dict(inputs.get(node.node_id, {}))
            for binding in bindings:
                values[binding.target_path[1:]] = None
            constraints = merge_constraints(proposal.goal.constraints,
                proposal.goal.constraints.model_copy(update={'allowed_executor_ids': [selected[node.node_id].executor_id]}))
            steps.append(WorkflowStep(step_id=node.node_id,
                action=ActionRequest(capability=node.capability, input=values, policy=proposal.goal.policy, context=node_context(node),
                    constraints=constraints), depends_on=sorted(dependencies), bindings=bindings))
        return WorkflowRequest(workflow_id=proposal.proposal_id, steps=steps,
            budget=WorkflowBudget(max_cash_usd=proposal.goal.limits.max_cash_usd),
            outputs=[WorkflowOutputProjection(name=node_id, step_id=node_id, path='') for node_id in proposal.goal.deliverables])
