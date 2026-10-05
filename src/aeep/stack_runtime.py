"""Content-free stack checkpoints around the existing workflow execution boundary."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

from .assessment.models import content_digest
from .economic.prepared import executor_fingerprint
from .errors import ConfigurationError
from .models import ExecutionStatus, ExecutorKind, SideEffect, utc_now
from .registry import validate_json
from .stack_models import ArtifactContract, StackProposal, StackRecovery
from .stack_planning import StackService, port_mapping
from .workflow import WorkflowBudget, WorkflowRequest, pointer_get, pointer_replace


def validate_artifact(value: Any, contract: ArtifactContract) -> None:
    if contract.value_schema is not None:
        validate_json(value, contract.value_schema, label='stack artifact')
    if contract.max_bytes is not None:
        encoded = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, allow_nan=False).encode()
        if len(encoded) > contract.max_bytes:
            raise ConfigurationError('materialized artifact exceeds its byte bound')
    if any(getattr(contract, key) is not None for key in ('max_width', 'max_height', 'max_duration_seconds')):
        raise ConfigurationError('media dimensions require a supported artifact verifier')


class StackRuntime:
    def __init__(self, service: StackService) -> None:
        self.service = service
        self.router = service.router
        self.store = service.router.store

    def assemble(self, identity: str, *, profile_id: str | None = None) -> dict[str, Any]:
        preflight = self.service.preflight(identity, task_profile=profile_id)
        if not preflight.ready:
            raise ConfigurationError('; '.join(preflight.blockers))
        proposal = self.service.inspect(identity)
        if proposal.goal.propose_only:
            raise ConfigurationError('goal is propose-only; create and review an executable successor')
        if profile_id is None:
            return {'assembled': True, 'activated': False, 'proposal_id': identity,
                    'authority': 'ordinary per-action operator ceiling; no standing task scope created',
                    'scope_requirements': preflight.scope_requirements}
        from . import profiles
        profile = profiles.load(self.router, profile_id)
        current = profiles.preflight(self.router, profile)
        if not current['ready']:
            raise ConfigurationError('; '.join(current['blockers']))
        from .models import TaskScope
        scope = TaskScope.model_validate(self.service.repository.get('task_scope', profile.scope_digest))
        if any(scope.executor_fingerprints.get(c.executor_id) != c.executor_fingerprint for c in proposal.components):
            raise ConfigurationError('profile does not cover exact stack executors')
        activation = profiles.activate(self.router, profile_id)
        self.router._task_activation_digest = content_digest(activation)
        self.router.bind_task_scope(scope.scope_id)
        return {'assembled': True, 'activated': True, 'activation_id': activation.activation_id,
                'proposal_id': identity}

    def amend(self, previous_id: str, successor_id: str) -> dict[str, Any]:
        """Adopt a reviewed successor while retaining consumed allowance and artifacts."""
        previous, successor = self.service.inspect(previous_id), self.service.inspect(successor_id)
        if successor.parent_id != previous_id:
            raise ConfigurationError('successor must name its predecessor')
        check = self.service.preflight(successor_id)
        if not check.ready:
            raise ConfigurationError('; '.join(check.blockers))
        if previous.goal.nodes != successor.goal.nodes or previous.goal.deliverables != successor.goal.deliverables:
            raise ConfigurationError('amendment must preserve the semantic task graph')
        before = {c.node_id: c for c in previous.components}
        after = {c.node_id: c for c in successor.components}
        changed = {key for key in before if key not in after or
                   before[key].executor_id != after[key].executor_id or
                   before[key].executor_fingerprint != after[key].executor_fingerprint or
                   before[key].ports_digest != after[key].ports_digest}
        before_edges = {(e.target_node, e.target_port): e for e in previous.edges}
        for edge in successor.edges:
            if before_edges.get((edge.target_node, edge.target_port)) != edge:
                changed.add(edge.target_node)
        # Propagate through the compiled graph, including inserted converters.
        dependencies = {node.node_id: set(node.depends_on) for node in successor.goal.nodes}
        for edge in successor.edges:
            source = edge.source_node
            if edge.converter_node:
                dependencies.setdefault(edge.converter_node, set()).add(source)
                source = edge.converter_node
            dependencies.setdefault(edge.target_node, set()).add(source)
        while True:
            descendants = {key for key, parents in dependencies.items() if parents & changed}
            if descendants <= changed:
                break
            changed.update(descendants)
        with self.store._immediate_transaction() as connection:
            row = connection.execute('SELECT * FROM stack_runs WHERE proposal_id=?', (previous_id,)).fetchone()
            if row is None or row['state'] not in {'paused', 'complete'}:
                raise ConfigurationError('predecessor must be stopped without uncertain or delegated work')
            progress = json.loads(row['progress_json'])
            if any(record['state'] not in {'complete', 'retryable'} for record in progress.values()):
                raise ConfigurationError('predecessor contains unresolved work')
            for node_id in changed & progress.keys():
                if progress[node_id]['state'] == 'complete':
                    original = before[node_id]
                    if not original.idempotent or original.side_effect.rank > SideEffect.READ.rank:
                        raise ConfigurationError('amendment cannot replay a completed consequential operation')
            preserved = {key: value for key, value in progress.items() if key not in changed and value['state'] == 'complete'}
            remaining = len(successor.components) - len(preserved)
            if row['attempts'] + remaining > successor.goal.limits.max_attempts:
                raise ConfigurationError('successor allowance does not cover consumed and remaining attempts')
            if connection.execute('SELECT 1 FROM stack_runs WHERE proposal_id=?', (successor_id,)).fetchone():
                raise ConfigurationError('successor already has execution state')
            connection.execute('INSERT INTO stack_runs VALUES (?, ?, ?, ?, ?, ?)',
                (successor_id, row['input_digest'], 'paused', row['attempts'], row['deadline'], json.dumps(preserved)))
            connection.execute("UPDATE stack_runs SET state='superseded' WHERE proposal_id=?", (previous_id,))
        return {'proposal_id': successor_id, 'previous_id': previous_id,
                'preserved_nodes': sorted(preserved), 'consumed_attempts': row['attempts'],
                'deadline_extended': False}

    def reconcile(self, recovery_id: str, output: Any) -> dict[str, Any]:
        """Recover a lost checkpoint only from completed receipts and reviewed output."""
        recovery = StackRecovery.model_validate(self.service.repository.get('stack_recovery', recovery_id))
        proposal = self.service.inspect(recovery.proposal_id)
        if not self.service.preflight(proposal.proposal_id).ready:
            raise ConfigurationError('proposal is no longer ready')
        if content_digest({'output': output}) != recovery.output_digest:
            raise ConfigurationError('reviewed recovery artifact does not match')
        component = next((item for item in proposal.components if item.node_id == recovery.node_id), None)
        if component is None:
            raise ConfigurationError('unknown recovery node')
        spec = self.router.registry.get(component.executor_id)
        if spec.output_schema is None:
            raise ConfigurationError('recovery requires output verification')
        validate_json(output, spec.output_schema, label='recovered node output')
        for port, contract in port_mapping(self.router, component.executor_id).outputs.items():
            if not isinstance(output, dict) or port not in output:
                raise ConfigurationError('recovered artifact port missing')
            validate_artifact(output[port], contract)
        digest = content_digest(recovery)
        with self.store._immediate_transaction() as connection:
            if not connection.execute('SELECT 1 FROM assessment_reviews WHERE digest=? AND revoked=0', (digest,)).fetchone():
                raise ConfigurationError('exact recovery observation requires operator review')
            row = connection.execute('SELECT * FROM stack_runs WHERE proposal_id=?', (proposal.proposal_id,)).fetchone()
            if row is None or row['state'] not in {'running', 'uncertain'}:
                raise ConfigurationError('stack has no interrupted claim to reconcile')
            progress = json.loads(row['progress_json'])
            record = progress.get(recovery.node_id)
            if record is None or record['state'] != 'started':
                raise ConfigurationError('node is not an interrupted dispatch')
            expected_action = 'stack_action_' + content_digest({'proposal': proposal.proposal_id,
                'step': recovery.node_id, 'attempt': record['attempts']})
            for receipt_id in recovery.receipt_ids:
                receipt = self.store.get_receipt(receipt_id)
                if (receipt is None or receipt.action_id != expected_action or
                        receipt.executor_id != component.executor_id or
                        receipt.executor_fingerprint != component.executor_fingerprint or
                        receipt.status != ExecutionStatus.SUCCESS or receipt.output_valid is not True or
                        receipt.task_valid is not True):
                    raise ConfigurationError('recovery requires verified successful receipts for this exact dispatch')
                prepared_id = receipt.metadata.get('prepared_id')
                if prepared_id is not None:
                    prepared = self.store.get_prepared_decision(prepared_id)
                    if prepared is None or prepared.state.value != 'SETTLED':
                        raise ConfigurationError('prepared dispatch must be settled before checkpoint recovery')
                attempt = (self.store.execution_attempt_for_prepared(prepared_id) if prepared_id else
                           self.store.execution_attempt_for_decision(receipt.decision_id))
                if attempt is not None and attempt.state.value != 'COMPLETED':
                    raise ConfigurationError('existing attempt recovery must complete first')
            progress[recovery.node_id] = {'state': 'complete', 'attempts': record['attempts'],
                'output_digest': recovery.output_digest, 'receipt_ids': recovery.receipt_ids,
                'recovery_digest': digest, 'history_receipt_ids': record.get('history_receipt_ids', [])}
            connection.execute("UPDATE stack_runs SET state='paused', progress_json=? WHERE proposal_id=?",
                (json.dumps(progress), proposal.proposal_id))
        return {'proposal_id': proposal.proposal_id, 'recovered_node': recovery.node_id,
                'recovery_digest': digest, 'allowance_refunded': False,
                'limitation': 'Output identity is an exact reviewed operator observation; receipts retain their original verification.'}

    def _claim(self, proposal: StackProposal, input_digest: str) -> None:
        with self.store._immediate_transaction() as connection:
            row = connection.execute('SELECT * FROM stack_runs WHERE proposal_id=?', (proposal.proposal_id,)).fetchone()
            if row is None:
                if proposal.parent_id and connection.execute('SELECT 1 FROM stack_runs WHERE proposal_id=?', (proposal.parent_id,)).fetchone():
                    raise ConfigurationError('executed predecessor requires explicit amendment; allowance cannot reset')
                connection.execute('INSERT INTO stack_runs VALUES (?, ?, ?, ?, ?, ?)',
                    (proposal.proposal_id, input_digest, 'running', 0,
                     (utc_now() + timedelta(seconds=proposal.goal.limits.max_elapsed_seconds)).isoformat(), '{}'))
            else:
                if row['input_digest'] != input_digest:
                    raise ConfigurationError('stack inputs changed; create a successor proposal')
                if row['state'] in {'running', 'uncertain', 'superseded'}:
                    raise ConfigurationError('stack has an active or uncertain dispatch; reconcile before resuming')
                if row['deadline'] <= utc_now().isoformat():
                    raise ConfigurationError('stack execution deadline expired')
                connection.execute("UPDATE stack_runs SET state='running' WHERE proposal_id=?", (proposal.proposal_id,))

    def _progress(self, identity: str) -> dict[str, Any]:
        with self.store._lock:
            row = self.store._connection.execute('SELECT progress_json FROM stack_runs WHERE proposal_id=?', (identity,)).fetchone()
        return json.loads(row[0]) if row else {}

    def _state(self, identity: str, state: str) -> None:
        with self.store._immediate_transaction() as connection:
            connection.execute('UPDATE stack_runs SET state=? WHERE proposal_id=?', (state, identity))

    def _reserve(self, proposal: StackProposal, node_id: str) -> None:
        with self.store._immediate_transaction() as connection:
            row = connection.execute('SELECT * FROM stack_runs WHERE proposal_id=?', (proposal.proposal_id,)).fetchone()
            if row is None or row['state'] != 'running' or row['attempts'] >= proposal.goal.limits.max_attempts:
                raise ConfigurationError('stack attempt allowance exhausted')
            if row['deadline'] <= utc_now().isoformat():
                raise ConfigurationError('stack execution deadline expired')
            progress = json.loads(row['progress_json'])
            if progress.get(node_id, {}).get('state') in {'started', 'uncertain', 'complete'}:
                raise ConfigurationError('node cannot be replayed')
            node_attempts = progress.get(node_id, {}).get('attempts', 0) + 1
            if node_attempts > 1 + proposal.goal.limits.retry_reserve:
                raise ConfigurationError('node retry reserve exhausted')
            previous = progress.get(node_id, {})
            history = [*previous.get('history_receipt_ids', []), *previous.get('receipt_ids', [])]
            progress[node_id] = {'state': 'started', 'attempts': node_attempts, 'history_receipt_ids': history}
            connection.execute('UPDATE stack_runs SET attempts=attempts+1, progress_json=? WHERE proposal_id=?',
                               (json.dumps(progress), proposal.proposal_id))

    def _complete(self, identity: str, node_id: str, output: Any, receipt_ids: list[str]) -> None:
        with self.store._immediate_transaction() as connection:
            row = connection.execute('SELECT progress_json FROM stack_runs WHERE proposal_id=?', (identity,)).fetchone()
            progress = json.loads(row[0])
            progress[node_id] = {'state': 'complete', 'attempts': progress[node_id].get('attempts', 1), 'output_digest': content_digest({'output': output}),
                                 'receipt_ids': receipt_ids, 'history_receipt_ids': progress[node_id].get('history_receipt_ids', [])}
            connection.execute('UPDATE stack_runs SET progress_json=? WHERE proposal_id=?', (json.dumps(progress), identity))

    async def run(self, identity: str, inputs: dict[str, dict[str, Any]], *,
                  completed_outputs: dict[str, Any] | None = None,
                  delegated_outputs: dict[str, Any] | None = None,
                  approved_side_effect: SideEffect = SideEffect.READ) -> dict[str, Any]:
        preflight = self.service.preflight(identity)
        if not preflight.ready:
            raise ConfigurationError('; '.join(preflight.blockers))
        proposal = self.service.inspect(identity)
        if proposal.goal.propose_only:
            raise ConfigurationError('goal is propose-only')
        if any(self.router.registry.get(c.executor_id).kind in {ExecutorKind.HTTP, ExecutorKind.MCP, ExecutorKind.MANAGED_HOST}
               for c in proposal.components):
            raise ConfigurationError('remote production execution requires a separately supported scoped adapter')
        if proposal.maximum_cash_usd != 0 or self.router.manifest.economic_evidence.enabled:
            raise ConfigurationError('first-release stack runtime requires confirmed-free ordinary execution')
        workflow = self.service.compile(identity, inputs)
        selected = {c.node_id: c for c in proposal.components}
        prior = self._progress(identity)
        outputs = dict(completed_outputs or {})
        delegated = dict(delegated_outputs or {})
        if set(delegated) - {key for key, value in prior.items() if value['state'] == 'waiting'}:
            raise ConfigurationError('delegated output does not belong to a selected waiting node')
        if set(outputs) - set(prior):
            raise ConfigurationError('unknown completed artifact')
        receipts: list[str] = []
        for node_id, record in prior.items():
            receipts.extend(record.get('history_receipt_ids', []))
            if record['state'] == 'waiting':
                if node_id not in delegated:
                    return {'proposal_id': identity, 'status': 'waiting', 'waiting_node': node_id,
                            'completed_outputs': outputs, 'receipt_ids': receipts}
                continue
            if record['state'] == 'retryable':
                spec = self.router.registry.get(selected[node_id].executor_id)
                if not spec.idempotent or spec.side_effect.rank > SideEffect.READ.rank:
                    raise ConfigurationError('retry requires idempotent read-only work')
                receipts.extend(record.get('receipt_ids', []))
                continue
            if record['state'] != 'complete':
                raise ConfigurationError('incomplete node requires reconciliation; no automatic replay')
            if node_id not in outputs or content_digest({'output': outputs[node_id]}) != record['output_digest']:
                raise ConfigurationError(f'{node_id}: matching completed artifact required; outputs are not stored')
            for receipt_id in record['receipt_ids']:
                receipt = self.store.get_receipt(receipt_id)
                if receipt is None or receipt.executor_id != selected[node_id].executor_id or receipt.status != ExecutionStatus.SUCCESS:
                    raise ConfigurationError('completed artifact receipt unavailable')
                receipts.append(receipt_id)
        self._claim(proposal, content_digest(inputs))
        dispatched = False
        try:
            for step in workflow.steps:
                if prior.get(step.step_id, {}).get('state') == 'complete':
                    continue
                check = self.service.preflight(identity)
                if not check.ready:
                    raise ConfigurationError('; '.join(check.blockers))
                action = step.action.model_copy(deep=True)
                for binding in step.bindings:
                    pointer_replace(action.input, binding.target_path,
                                    pointer_get(outputs[binding.source_step_id], binding.source_path))
                component = selected[step.step_id]
                spec = self.router.registry.get(component.executor_id)
                if (executor_fingerprint(spec) != component.executor_fingerprint or
                        content_digest(port_mapping(self.router, spec.id)) != component.ports_digest):
                    raise ConfigurationError('executor or artifact contract drift before dispatch')
                # Validate real inputs before reserving. Selection stays pinned even
                # when other routes are individually cheaper at execution time.
                validate_json(action.input, spec.input_schema, label='stack node input')
                for port, contract in port_mapping(self.router, component.executor_id).inputs.items():
                    if port not in action.input:
                        raise ConfigurationError('required artifact input is missing')
                    validate_artifact(action.input[port], contract)
                is_waiting = prior.get(step.step_id, {}).get('state') == 'waiting'
                node_attempt = prior.get(step.step_id, {}).get('attempts', 0) + (0 if is_waiting else 1)
                action.action_id = 'stack_action_' + content_digest({'proposal': identity, 'step': step.step_id, 'attempt': node_attempt})
                action.idempotency_key = f'{identity}:{step.step_id}:{node_attempt}'
                action.constraints.max_cost_usd = 0
                decision = self.router.route(action)
                if decision.selected_executor_id != component.executor_id:
                    raise ConfigurationError('selected implementation no longer feasible')
                step_copy = step.model_copy(deep=True)
                step_copy.action, step_copy.bindings, step_copy.depends_on = action, [], []
                child = WorkflowRequest(workflow_id=identity + ':' + step.step_id,
                    steps=[step_copy], budget=WorkflowBudget(max_cash_usd=Decimal(0)))
                if not is_waiting:
                    self._reserve(proposal, step.step_id)
                dispatched = True
                with self.store._lock:
                    deadline = self.store._connection.execute('SELECT deadline FROM stack_runs WHERE proposal_id=?', (identity,)).fetchone()[0]
                from datetime import datetime
                timeout = min(proposal.goal.limits.max_attempt_seconds,
                              (datetime.fromisoformat(deadline) - utc_now()).total_seconds())
                async with asyncio.timeout(max(0, timeout)):
                    if is_waiting:
                        from .workflow import WorkflowExecutionOutcome, WorkflowStatus
                        record = prior[step.step_id]
                        if record['workflow_hash'] != child.workflow_hash:
                            raise ConfigurationError('waiting workflow input binding changed')
                        waiting = WorkflowExecutionOutcome(workflow_id=child.workflow_id, workflow_hash=child.workflow_hash,
                            status=WorkflowStatus.WAITING, waiting_step_id=step.step_id,
                            waiting_decision_id=record['decision_id'])
                        result = await self.router.resume_workflow(child, waiting, step_id=step.step_id,
                            output=delegated[step.step_id], approved_side_effect=approved_side_effect)
                    else:
                        result = await self.router.execute_workflow(child, approved_side_effect=approved_side_effect,
                            require_prepared=spec.kind not in {ExecutorKind.HOST, ExecutorKind.DELEGATE})
                if result.status.value == 'waiting':
                    with self.store._immediate_transaction() as connection:
                        row = connection.execute('SELECT progress_json FROM stack_runs WHERE proposal_id=?', (identity,)).fetchone()
                        progress = json.loads(row[0])
                        progress[step.step_id] = {'state': 'waiting', 'attempts': node_attempt,
                            'decision_id': result.waiting_decision_id, 'workflow_hash': child.workflow_hash,
                            'history_receipt_ids': progress[step.step_id].get('history_receipt_ids', [])}
                        connection.execute("UPDATE stack_runs SET state='waiting', progress_json=? WHERE proposal_id=?", (json.dumps(progress), identity))
                    return {'proposal_id': identity, 'status': 'waiting', 'waiting_node': step.step_id,
                            'decision_id': result.waiting_decision_id, 'completed_outputs': outputs, 'receipt_ids': receipts}
                if result.status.value != 'success':
                    failed_receipts = [r.receipt_id for r in result.receipts]
                    receipts.extend(failed_receipts)
                    safe_retry = (spec.idempotent and spec.side_effect.rank <= SideEffect.READ.rank and
                                  bool(result.receipts) and all(r.status in {ExecutionStatus.FAILED, ExecutionStatus.REJECTED}
                                      for r in result.receipts) and node_attempt <= proposal.goal.limits.retry_reserve)
                    if safe_retry:
                        with self.store._immediate_transaction() as connection:
                            row = connection.execute('SELECT progress_json FROM stack_runs WHERE proposal_id=?', (identity,)).fetchone()
                            progress = json.loads(row[0])
                            progress[step.step_id] = {'state': 'retryable', 'attempts': node_attempt, 'receipt_ids': failed_receipts,
                                'history_receipt_ids': progress[step.step_id].get('history_receipt_ids', [])}
                            connection.execute('UPDATE stack_runs SET progress_json=? WHERE proposal_id=?', (json.dumps(progress), identity))
                        dispatched = False
                    self._state(identity, 'paused' if safe_retry else 'uncertain')
                    return {'proposal_id': identity, 'status': 'paused' if safe_retry else 'needs_recovery',
                            'completed_outputs': outputs, 'receipt_ids': receipts,
                            'blocked_node': step.step_id, 'error': 'node did not complete; no automatic replay'}
                output = result.step_outputs[step.step_id]
                mapping = port_mapping(self.router, component.executor_id)
                if not isinstance(output, dict) or not mapping.outputs.keys() <= output.keys():
                    raise ConfigurationError('node output does not satisfy its artifact ports')
                for port, contract in mapping.outputs.items():
                    validate_artifact(output[port], contract)
                node_receipts = [receipt.receipt_id for receipt in result.receipts]
                if not node_receipts or any(r.output_valid is False or r.task_valid is False for r in result.receipts):
                    raise ConfigurationError('node verification failed')
                self._complete(identity, step.step_id, output, node_receipts)
                dispatched = False
                outputs[step.step_id] = output
                receipts.extend(node_receipts)
            self._state(identity, 'complete')
            return {'proposal_id': identity, 'status': 'complete',
                    'outputs': {key: outputs[key] for key in proposal.goal.deliverables},
                    'completed_outputs': outputs, 'receipt_ids': receipts,
                    'verification_limits': ['Synthetic checks do not establish provider quality or comparative benefit.']}
        except ConfigurationError:
            self._state(identity, 'uncertain' if dispatched else 'paused')
            return {'proposal_id': identity, 'status': 'needs_recovery' if dispatched else 'paused',
                    'completed_outputs': outputs, 'receipt_ids': receipts,
                    'error': 'runtime precondition or verification failed; inspect preflight and receipts'}
        except BaseException:
            self._state(identity, 'uncertain' if dispatched else 'paused')
            raise
