"""Inert stack contracts. Task values are supplied separately at execution time."""
from __future__ import annotations

from decimal import Decimal
from graphlib import CycleError, TopologicalSorter
from typing import Any, Literal

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import Field, model_validator

from .models import ActionConstraints, ResourceVector, SideEffect, StrictModel

Identifier = str


class ArtifactContract(StrictModel):
    semantic_type: str = Field(min_length=1, max_length=200)
    media_type: str | None = Field(default=None, max_length=200)
    value_schema: dict[str, Any] | None = None
    encoding: str | None = None
    max_bytes: int | None = Field(default=None, ge=0)
    max_width: int | None = Field(default=None, ge=0)
    max_height: int | None = Field(default=None, ge=0)
    max_duration_seconds: float | None = Field(default=None, ge=0)
    locality: Literal['local', 'remote'] | None = None
    confidentiality: Literal['public', 'private', 'restricted'] | None = None


    @model_validator(mode='after')
    def valid_schema(self) -> ArtifactContract:
        if self.value_schema is not None:
            try:
                validator_for(self.value_schema).check_schema(self.value_schema)
            except SchemaError as exc:
                raise ValueError('invalid artifact schema') from exc
        return self


class StackBinding(StrictModel):
    source_node: str
    source_port: str
    target_port: str


class TaskNode(StrictModel):
    node_id: str = Field(pattern=r'^[A-Za-z0-9_.:-]+$', max_length=100)
    capability: str = Field(pattern=r'^[a-z0-9][a-z0-9_.-]*@[0-9]+(?:\.[0-9]+){0,2}$')
    inputs: dict[str, ArtifactContract] = Field(default_factory=dict, max_length=32)
    outputs: dict[str, ArtifactContract] = Field(default_factory=dict, max_length=32)
    bindings: list[StackBinding] = Field(default_factory=list, max_length=32)
    depends_on: list[str] = Field(default_factory=list, max_length=64)
    verification_required: bool = True

    @model_validator(mode='after')
    def ports(self) -> TaskNode:
        if any(not key or '/' in key or '~' in key for key in {*self.inputs, *self.outputs}):
            raise ValueError('ports must be nonempty simple property names')
        targets = [binding.target_port for binding in self.bindings]
        if len(set(targets)) != len(targets) or not set(targets) <= self.inputs.keys():
            raise ValueError('bindings require distinct declared input ports')
        return self


class StackLimits(StrictModel):
    max_cash_usd: Decimal = Field(default=Decimal(0), ge=0)
    max_attempts: int = Field(default=64, ge=1, le=1000)
    max_attempt_seconds: float = Field(default=60, gt=0, le=3600)
    max_elapsed_seconds: float = Field(default=3600, gt=0, le=86400)
    retry_reserve: int = Field(default=0, ge=0, le=9)


class GoalSpec(StrictModel):
    schema_version: Literal['aeep.goal.v1'] = 'aeep.goal.v1'
    goal_id: str = Field(pattern=r'^[A-Za-z0-9_.:-]+$', max_length=100)
    nodes: list[TaskNode] = Field(min_length=1, max_length=64)
    deliverables: list[str] = Field(min_length=1, max_length=64)
    constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    limits: StackLimits = Field(default_factory=StackLimits)
    policy: str = Field(default='balanced', max_length=100)
    propose_only: bool = True

    @model_validator(mode='after')
    def graph(self) -> GoalSpec:
        if any(node.node_id.startswith('convert:') for node in self.nodes):
            raise ValueError('convert: node namespace is reserved')
        nodes = {node.node_id: node for node in self.nodes}
        if len(nodes) != len(self.nodes) or not set(self.deliverables) <= nodes.keys():
            raise ValueError('duplicate nodes or unknown deliverable')
        dependencies: dict[str, set[str]] = {}
        for node in self.nodes:
            deps = {*node.depends_on, *(binding.source_node for binding in node.bindings)}
            if not deps <= nodes.keys():
                raise ValueError('unknown dependency')
            for binding in node.bindings:
                if binding.source_port not in nodes[binding.source_node].outputs:
                    raise ValueError('unknown source port')
            dependencies[node.node_id] = deps
        try:
            tuple(TopologicalSorter(dependencies).static_order())
        except CycleError as exc:
            raise ValueError('stack contains a dependency cycle') from exc
        return self

    def ordered_nodes(self) -> list[TaskNode]:
        by_id = {node.node_id: node for node in self.nodes}
        remaining = set(by_id)
        ordered: list[TaskNode] = []
        while remaining:
            ready = sorted(key for key in remaining if not (
                {*by_id[key].depends_on, *(b.source_node for b in by_id[key].bindings)} & remaining))
            ordered.extend(by_id[key] for key in ready)
            remaining.difference_update(ready)
        return ordered


class StackPlanningConfig(StrictModel):
    """Operator configuration, never supplied by a model-facing call."""
    candidates_per_node: int = Field(default=8, ge=1, le=32)
    beam_width: int = Field(default=32, ge=1, le=128)
    max_expansions: int = Field(default=16384, ge=1, le=262144)
    max_seconds: float = Field(default=10, gt=0, le=30)
    max_goal_bytes: int = Field(default=131072, ge=1024, le=1048576)
    converter_ids: list[str] = Field(default_factory=list, max_length=32)


class StackPortMapping(StrictModel):
    inputs: dict[str, ArtifactContract] = Field(default_factory=dict)
    outputs: dict[str, ArtifactContract] = Field(default_factory=dict)
    setup_ids: list[str] = Field(default_factory=list, max_length=16)


class StackComponent(StrictModel):
    node_id: str
    executor_id: str
    executor_fingerprint: str
    ports_digest: str
    side_effect: SideEffect
    idempotent: bool
    score: float
    estimated: ResourceVector
    expected_cash_usd: Decimal | None = None
    maximum_cash_usd: Decimal | None = None
    no_additional_capability: bool = True
    setup_ids: list[str] = Field(default_factory=list)
    evidence_basis: Literal['configured', 'admitted'] = 'configured'
    evidence_refs: list[str] = Field(default_factory=list)


class CompatibilityEdge(StrictModel):
    source_node: str
    source_port: str
    target_node: str
    target_port: str
    verdict: Literal['compatible', 'incompatible', 'unknown']
    reasons: list[str] = Field(default_factory=list)
    converter_id: str | None = None
    converter_node: str | None = None


class StackProposal(StrictModel):
    schema_version: Literal['aeep.stack-proposal.v1'] = 'aeep.stack-proposal.v1'
    proposal_id: str
    goal_digest: str
    goal: GoalSpec
    manifest_digest: str
    components: list[StackComponent] = Field(default_factory=list)
    edges: list[CompatibilityEdge] = Field(default_factory=list)
    estimated: ResourceVector = Field(default_factory=ResourceVector)
    expected_cash_usd: Decimal | None = None
    maximum_cash_usd: Decimal | None = None
    status: Literal['READY', 'NEEDS_SETUP', 'NEEDS_ASSESSMENT', 'BLOCKED']
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    alternatives: dict[str, list[str]] = Field(default_factory=dict)
    search_complete: bool = True
    expansions: int = 0
    parent_id: str | None = None


class StackPreflight(StrictModel):
    schema_version: Literal['aeep.stack-preflight.v1'] = 'aeep.stack-preflight.v1'
    proposal_id: str
    proposal_digest: str
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scope_requirements: dict[str, Any] = Field(default_factory=dict)
    setup_requirements: list[dict[str, Any]] = Field(default_factory=list)


class StackReference(StrictModel):
    proposal_id: str


class StackOptimizeRequest(StackReference):
    policy: str


class StackRunRequest(StackReference):
    inputs: dict[str, dict[str, Any]]


class StackRecovery(StrictModel):
    """Exact operator observation; cannot settle an uncertain external operation."""
    schema_version: Literal['aeep.stack-recovery.v1'] = 'aeep.stack-recovery.v1'
    recovery_id: str = Field(pattern=r'^[A-Za-z0-9_.:-]+$', max_length=100)
    proposal_id: str
    node_id: str
    output_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    receipt_ids: list[str] = Field(min_length=1, max_length=10)
    coordinator_stopped: Literal[True]
