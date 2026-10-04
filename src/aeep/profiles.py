"""Pinned capability views over the existing task authority and activation lifecycle.

Profiles are operator definitions, never grants. Unknown host state stays unknown;
the supported enforcement boundary is the existing AEEP task service.
"""

from __future__ import annotations

from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from .assessment.models import Digest, content_digest
from .assessment.repository import AssessmentRepository
from .assessment.tools import declarations
from .economic.prepared import executor_fingerprint
from .errors import AEEPError, ConfigurationError
from .models import SideEffect, StrictModel, TaskScope, utc_now

if TYPE_CHECKING:
    from .mcp.server import AEEPToolService
    from .router import Router
    from .tasks import TaskActivation


class ProfileComponent(StrictModel):
    component_id: str = Field(min_length=1, max_length=200)
    resource_id: str = Field(min_length=1, max_length=500)
    version: str | None = Field(default=None, max_length=200)
    content_digest: Digest
    kind: Literal['executor', 'skill', 'server', 'file', 'hook', 'dependency', 'package']
    dependencies: list[str] = Field(default_factory=list, max_length=128)
    executor_id: str | None = Field(default=None, min_length=1, max_length=200)
    removal: Literal['available', 'deferred', 'hidden', 'call_blocked', 'absent'] = 'available'
    # Claims are retained as intended state, never reported as host observations.
    discoverable: bool = False
    exposed: bool = False

    @model_validator(mode='after')
    def identity(self) -> ProfileComponent:
        if (self.kind == 'executor') != (self.executor_id is not None):
            raise ValueError('only executor components bind an executor_id')
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError('duplicate component dependencies')
        if self.removal in {'hidden', 'call_blocked', 'absent'} and self.exposed:
            raise ValueError('excluded components cannot request exposure')
        if self.removal == 'absent' and self.discoverable:
            raise ValueError('absent components cannot request discovery')
        return self


class CapabilityProfile(StrictModel):
    schema_version: Literal['aeep.capability-profile.v1'] = 'aeep.capability-profile.v1'
    profile_id: str = Field(min_length=1, max_length=200)
    scope_digest: Digest
    manifest_digest: Digest
    tool_schema_digest: Digest
    components: list[ProfileComponent] = Field(min_length=1, max_length=128)
    host: Literal['codex-project', 'task-service'] = 'codex-project'
    # This host is already running. A profile must not pretend to choose its model.
    intended_model: str | None = Field(default=None, min_length=1, max_length=200)
    intended_effort: str | None = Field(default=None, min_length=1, max_length=100)
    strict_isolation: bool = False
    required_host_features: list[Literal['catalog_filtering', 'schema_exposure', 'skill_file_exclusion',
        'call_enforcement', 'filesystem_isolation', 'network_isolation', 'credential_scope',
        'hooks', 'context_reset', 'resource_observability']] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def dependency_integrity(self) -> CapabilityProfile:
        components = {item.component_id: item for item in self.components}
        if len(components) != len(self.components):
            raise ValueError('duplicate profile component identity')
        executors = [item.executor_id for item in self.components if item.executor_id]
        if len(executors) != len(set(executors)):
            raise ValueError('an executor cannot have contradictory component states')
        for item in self.components:
            if not set(item.dependencies).issubset(components):
                raise ValueError('profile dependency is missing')
            if item.removal == 'available' and any(components[key].removal != 'available' for key in item.dependencies):
                raise ValueError('available component depends on an excluded component')
        try:
            tuple(TopologicalSorter({key: item.dependencies for key, item in components.items()}).static_order())
        except CycleError as exc:
            raise ValueError('profile dependencies contain a cycle') from exc
        return self


def _profile(router: Router, value: CapabilityProfile | str) -> CapabilityProfile:
    if isinstance(value, CapabilityProfile):
        return CapabilityProfile.model_validate(value.model_dump())
    return CapabilityProfile.model_validate(AssessmentRepository(router.store).get('capability_profile', value))


def load(router: Router, identity: str) -> CapabilityProfile:
    return _profile(router, identity)


def _reviewed(router: Router, digest: str) -> bool:
    with router.store._lock:
        row = router.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?', (digest,)).fetchone()
    return row is not None and not row[0]


def _tools(router: Router, scope: TaskScope) -> list[dict[str, Any]]:
    capabilities = {router.registry.get(key).capability for key, fingerprint in scope.executor_fingerprints.items()
                    if router.registry.contains(key) and executor_fingerprint(router.registry.get(key)) == fingerprint}
    return declarations(router.store, tasks_only=True, capabilities=capabilities)


def from_scope(router: Router, scope_id: str, *, profile_id: str,
               host: Literal['codex-project', 'task-service'] = 'codex-project') -> CapabilityProfile:
    """Build an inert default profile; saving/review/activation remain explicit."""
    scope = TaskScope.model_validate(AssessmentRepository(router.store).get('task_scope', scope_id))
    return CapabilityProfile(profile_id=profile_id, host=host, scope_digest=content_digest(scope),
        manifest_digest=content_digest(router.manifest), tool_schema_digest=content_digest({'tools': _tools(router, scope)}),
        components=[ProfileComponent(component_id=key, resource_id=key, content_digest=fingerprint.removeprefix('sha256:'),
            kind='executor', executor_id=key, exposed=True) for key, fingerprint in sorted(scope.executor_fingerprints.items())])


def define(router: Router, profile: CapabilityProfile) -> str:
    profile = _profile(router, profile)
    return AssessmentRepository(router.store).put('capability_profile', profile.profile_id, profile)


def compile_profile(router: Router, profile: CapabilityProfile | str) -> dict[str, Any]:
    """Read-only resolution. Does not bind a router, launch a host or probe tools."""
    profile = _profile(router, profile)
    scope = TaskScope.model_validate(AssessmentRepository(router.store).get('task_scope', profile.scope_digest))
    blockers: list[str] = []
    if content_digest(scope) != profile.scope_digest or content_digest(router.manifest) != profile.manifest_digest:
        blockers.append('profile scope or manifest binding changed')
    if router.manifest_path is None or str(router.manifest_path.parent) != scope.project_root:
        blockers.append('profile belongs to another project')
    if router.store.path == ':memory:':
        blockers.append('task profiles require durable attempt storage')
    if utc_now() >= scope.expires_at:
        blockers.append('task scope expired')
    if router._task_scope_digest not in {None, profile.scope_digest}:
        blockers.append('session already bound to another task scope')
    selected = {item.executor_id for item in profile.components if item.kind == 'executor' and item.removal == 'available'}
    if selected != set(scope.executor_fingerprints):
        blockers.append('available profile executors must exactly match task authority')
    tools = _tools(router, scope)
    selected_capabilities = {router.registry.get(key).capability for key in selected
                             if key is not None and router.registry.contains(key)}
    if not tools:
        blockers.append('task scope exposes no supported task tool definitions')
    if content_digest({'tools': tools}) != profile.tool_schema_digest:
        blockers.append('task tool definitions changed')
    support: dict[str, str] = dict(catalog_filtering='unsupported', schema_exposure='supported',
        skill_file_exclusion='unsupported', call_enforcement='supported', filesystem_isolation='unknown',
        network_isolation='unknown', credential_scope='unknown', hooks='unsupported',
        context_reset='unsupported', resource_observability='unknown')
    if profile.strict_isolation:
        blockers.append('strict whole-host isolation is unsupported by the project task service')
    if profile.intended_model is not None or profile.intended_effort is not None:
        blockers.append('project activation cannot enforce the running host model or effort')
    for feature in profile.required_host_features:
        if support[feature] != 'supported':
            blockers.append(f'required host feature is {support[feature]}: {feature}')
    resolved: list[dict[str, Any]] = []
    dependencies = {key for component in profile.components if component.removal == 'available'
                    for key in component.dependencies}
    for component in profile.components:
        item: dict[str, Any] = {'component': component.model_dump(mode='json'), 'installed': None,
            'registered': None, 'discoverable': None, 'permitted': None, 'configured_permitted': False, 'exposed': None,
            'used': None, 'removal_effective': None, 'scope': 'AEEP task service only'}
        key = component.executor_id
        if component.discoverable:
            blockers.append(f'{component.component_id}: host discovery configuration unsupported')
        if component.removal in {'deferred', 'absent'}:
            blockers.append(f'{component.component_id}: {component.removal} cannot be enforced across host access paths')
        if component.kind != 'executor':
            if component.component_id in dependencies:
                blockers.append(f'{component.component_id}: required dependency has no verified runtime binding')
            if component.exposed or component.removal != 'available':
                blockers.append(f'{component.component_id}: non-executor control unsupported')
            resolved.append(item)
            continue
        assert key is not None
        item['registered'] = router.registry.contains(key)
        if item['registered']:
            spec = router.registry.get(key)
            if component.removal == 'hidden' and spec.capability in selected_capabilities:
                blockers.append(f'{key}: capability schema remains exposed through another scoped executor')
            fingerprint = executor_fingerprint(spec)
            if fingerprint.removeprefix('sha256:') != component.content_digest:
                blockers.append(f'{key}: component fingerprint changed')
            if key in selected:
                if scope.executor_fingerprints.get(key) != fingerprint:
                    blockers.append(f'{key}: task executor fingerprint changed')
                if not component.exposed:
                    blockers.append(f'{key}: task service exposes every scoped capability')
                if spec.side_effect.rank > scope.approval_ceiling.rank:
                    blockers.append(f'{key}: executor exceeds task approval ceiling')
                if not spec.enabled:
                    blockers.append(f'{key}: executor disabled')
                if not declarations(router.store, tasks_only=True, capabilities={spec.capability}):
                    blockers.append(f'{key}: capability has no supported task tool definition')
            item.update(capability=spec.capability, allowed_operation=spec.capability,
                side_effect=spec.side_effect.value, requires_network=spec.requires_network,
                native_boundary=spec.config.get('native_sandbox'), configured_permitted=key in selected,
                configured_exposure=key in selected)
        elif key in selected:
            blockers.append(f'{key}: executor unavailable')
        if component.removal in {'hidden', 'call_blocked'}:
            item['removal_effective'] = 'call_blocked within AEEP task authority; other host paths unknown'
        resolved.append(item)
    return dict(profile=profile.model_dump(mode='json'), profile_digest=content_digest(profile),
        scope=scope.model_dump(mode='json'), tools=tools, components=resolved, host_support=support,
        host_version=None, support_scope='AEEP task service; not the entire Codex host',
        host_binding=profile.host == 'codex-project',
        schema_exposure_scope='service declarations; host ingestion and model exposure unknown',
        blockers=list(dict.fromkeys(blockers)), ready=not blockers, activated=False,
        limits={'max_attempts': scope.max_attempts, 'max_attempt_seconds': scope.max_attempt_seconds,
                'approval_ceiling': scope.approval_ceiling.value, 'expires_at': scope.expires_at.isoformat()},
        unknowns=['host effective inventory', 'loaded model context', 'installed package files',
                  'credential access outside the task child', 'complete resource telemetry'])


def preflight(router: Router, profile: CapabilityProfile | str) -> dict[str, Any]:
    result = compile_profile(router, profile)
    for kind, digest in [('capability profile', result['profile_digest']), ('task scope', result['profile']['scope_digest'])]:
        if not _reviewed(router, digest):
            result['blockers'].append(f'{kind} requires current exact operator review')
    result['ready'] = not result['blockers']
    result['execution_readiness'] = 'activation also checks qualification, admission, backend and scope'
    return result


def require_profile(router: Router, identity: str, scope_digest: str) -> CapabilityProfile:
    """Called by the existing activation/dispatch boundary, never by model policy."""
    profile = _profile(router, identity)
    if profile.scope_digest != scope_digest:
        raise ConfigurationError('profile cannot replace task authority')
    result = preflight(router, profile)
    if not result['ready']:
        raise ConfigurationError('; '.join(result['blockers']))
    return profile


def activate(router: Router, profile_id: str, *, replace: str | None = None) -> TaskActivation:
    from .tasks import activate as activate_task
    profile = _profile(router, profile_id)
    return activate_task(router, profile.scope_digest, replace=replace, capability_profile_digest=content_digest(profile),
                         host_binding=profile.host == 'codex-project')


def bind_service(router: Router, profile_id: str, *,
                 approved_side_effect: SideEffect = SideEffect.READ) -> tuple[TaskActivation, AEEPToolService]:
    """Use production activation in a caller-owned assessment or local service.

    Requires an explicitly reviewed task-service profile. The caller tears down
    the returned activation after closing its service. No host configuration is
    installed, no trial starts, and the existing scope keeps all used allowances.
    """
    from .mcp.server import AEEPToolService
    from .tasks import change_state
    profile = load(router, profile_id)
    if profile.host != 'task-service':
        raise ConfigurationError('execution-local service requires a task-service profile')
    activation = activate(router, profile_id)
    try:
        service = AEEPToolService(router, profile='task', task_activation=activation.activation_id,
                                  approved_side_effect=approved_side_effect)
    except Exception:
        change_state(router, activation.activation_id, 'rollback')
        raise
    return activation, service


def inspect(router: Router, profile_id: str, *, activation_id: str | None = None) -> dict[str, Any]:
    result = preflight(router, profile_id)
    if activation_id is None:
        return result
    from .tasks import TaskActivation, require_activation
    from .tasks import inspect as inspect_task
    record = TaskActivation.model_validate(AssessmentRepository(router.store).get('task_activation', activation_id))
    if record.capability_profile_digest != result['profile_digest']:
        raise ConfigurationError('activation belongs to another capability profile')
    result['activation'] = inspect_task(router, activation_id)
    try:
        require_activation(router, activation_id)
        result['activated'] = True
    except AEEPError as exc:
        result['blockers'].append(str(exc))
    with router.store._lock:
        rows = router.store._connection.execute(
            "SELECT executor_id,COUNT(*) FROM receipts WHERE json_extract(payload_json,'$.metadata.task_scope_digest')=? "
            "AND json_extract(payload_json,'$.transport_success')=1 GROUP BY executor_id",
            (record.scope_digest,)).fetchall()
    counts = dict(rows)
    for item in result['components']:
        key = item['component']['executor_id']
        item['scope_transport_success_receipts'] = counts.get(key, 0)
        item['usage_observation_scope'] = 'task scope; not attributable to a particular profile activation'
        # Positive receipt observation only. Missing records do not prove non-use.
        item['used'] = True if counts.get(key, 0) else None
        item['permitted'] = item['configured_permitted'] and result['activated']
    result['ready'] = not result['blockers']
    return result


def teardown(router: Router, activation_id: str) -> dict[str, object]:
    from .tasks import change_state
    return change_state(router, activation_id, 'uninstall')


def diff_profiles(left: CapabilityProfile, right: CapabilityProfile) -> dict[str, Any]:
    left, right = CapabilityProfile.model_validate(left.model_dump()), CapabilityProfile.model_validate(right.model_dump())
    before = {item.component_id: item.model_dump(mode='json') for item in left.components}
    after = {item.component_id: item.model_dump(mode='json') for item in right.components}
    common = before.keys() & after.keys()
    return dict(before_digest=content_digest(left), after_digest=content_digest(right),
        added=[after[key] for key in sorted(after.keys() - before.keys())],
        removed=[before[key] for key in sorted(before.keys() - after.keys())],
        changed=[{'before': before[key], 'after': after[key]} for key in sorted(common) if before[key] != after[key]],
        configuration_changes={key: {'before': getattr(left, key), 'after': getattr(right, key)}
            for key in CapabilityProfile.model_fields if key not in {'profile_id', 'components'} and getattr(left, key) != getattr(right, key)},
        identical=content_digest(left) == content_digest(right), evidence='declared configuration; effective host differences remain separately verified')


def _self_check() -> None:
    """Bounded data-only check: dependency cycles and contradictory removal fail."""
    from pydantic import ValidationError
    digest = '0' * 64
    a = ProfileComponent(component_id='a', resource_id='a', content_digest=digest, kind='dependency', dependencies=['b'])
    b = ProfileComponent(component_id='b', resource_id='b', content_digest=digest, kind='dependency', dependencies=['a'])
    try:
        CapabilityProfile(profile_id='cycle', scope_digest=digest, manifest_digest=digest, tool_schema_digest=digest, components=[a, b])
    except ValidationError:
        pass
    else:
        raise AssertionError('cyclic profile accepted')
    try:
        ProfileComponent(component_id='a', resource_id='a', content_digest=digest, kind='skill', removal='absent', exposed=True)
    except ValidationError:
        pass
    else:
        raise AssertionError('absent exposed component accepted')


if __name__ == '__main__':
    _self_check()
