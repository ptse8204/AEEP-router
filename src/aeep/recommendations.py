"""Inert recommendations over discovered metadata; executable stacks stay separate."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .assessment.repository import AssessmentRepository
from .catalogs import search_catalogs
from .discovery import DiscoveryRequest, RegistryCandidate
from .discovery_service import DiscoveryConfig
from .errors import ConfigurationError
from .models import StrictModel, new_id, utc_now
from .router import Router


class HostCapability(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=1000)
    kind: Literal['tool', 'skill', 'hook'] = 'tool'
    availability: Literal['configured', 'observed', 'unknown'] = 'unknown'
    source: str = Field(min_length=1, max_length=2048)


class RecommendationStage(StrictModel):
    stage_id: str = Field(pattern=r'^[a-z0-9_-]{1,80}$')
    purpose: str = Field(min_length=1, max_length=500)
    search_terms: list[str] = Field(min_length=1, max_length=6)
    capability: str | None = Field(default=None, max_length=200)
    preferred_candidate: str | None = Field(default=None, max_length=300)
    selection_reason: str | None = Field(default=None, max_length=1000)

    @field_validator('purpose')
    @classmethod
    def public_purpose(cls, value: str) -> str:
        return DiscoveryRequest.public_phrase(value)

    @field_validator('search_terms')
    @classmethod
    def public_terms(cls, values: list[str]) -> list[str]:
        return [DiscoveryRequest.public_phrase(value) for value in values]


class RecommendationRequest(StrictModel):
    host: Literal['codex', 'claude', 'dsh', 'deepseek-api']
    stages: list[RecommendationStage] = Field(min_length=1, max_length=16)
    priorities: list[Literal['quality', 'cost', 'privacy', 'setup', 'speed']] = Field(default=['quality', 'setup'])
    host_capabilities: list[HostCapability] = Field(default_factory=list, max_length=100)
    web_candidates: list[RegistryCandidate] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique_stages(self) -> RecommendationRequest:
        if len({s.stage_id for s in self.stages}) != len(self.stages):
            raise ValueError('stage IDs must be unique')
        return self


class RecommendationOption(StrictModel):
    candidate_id: str
    name: str
    source: str
    reason: str
    evidence_basis: Literal['configured', 'host_reported', 'registry_claim', 'web_claim']
    readiness: Literal['configured', 'host_reported', 'setup_required', 'incompatible']
    compatibility: Literal['supported_host_claim', 'incompatible_host', 'unknown'] = 'unknown'
    quality: str = 'unknown; inspect samples or applicable assessment evidence'
    cost: str = 'unknown; check current provider terms'
    privacy: str = 'unknown; check data flow and provider terms'
    dependencies: list[str] = Field(default_factory=list)
    next_action: str


class StageRecommendation(StrictModel):
    stage_id: str
    purpose: str
    preferred: str | None
    options: list[RecommendationOption]
    blockers: list[str]


class StackRecommendation(StrictModel):
    schema_version: Literal['aeep.stack-recommendation.v1'] = 'aeep.stack-recommendation.v1'
    recommendation_id: str
    created_at: datetime
    host: str
    priorities: list[str]
    status: Literal['recommendation_ready', 'setup_required', 'blocked']
    stages: list[StageRecommendation]
    search_ids: list[str]
    warnings: list[str]


async def recommend(router: Router, request: RecommendationRequest, *, config: DiscoveryConfig | None = None) -> StackRecommendation:
    stages, searches, warnings = [], [], []
    # A single bounded search batch serves all stages; the host can refine terms in a successor.
    terms = list(dict.fromkeys(term for stage in request.stages for term in stage.search_terms))
    if len(terms) > 6:
        warnings.append('Only the first six distinct terms were searched; refine unresolved stages in a successor.')
    found = await search_catalogs(router.store, terms[:6], config=config)
    searches.append(found.search_id)
    warnings.extend(found.warnings)
    candidates = {c.registry_candidate_id: c for c in found.candidates}
    for candidate in request.web_candidates:
        from .marketplaces import public_url
        source = candidate.source_repository or candidate.remote_endpoint
        if not source:
            raise ConfigurationError('web candidates require a public source URL')
        public_url(source)
        # Host-provided web claims cannot overwrite a registry snapshot.
        if candidate.registry_candidate_id in candidates:
            raise ConfigurationError('web candidate conflicts with a discovered identity')
        existing = router.store.get_registry_candidate(candidate.registry_candidate_id)
        if existing and existing.raw_metadata_digest != candidate.raw_metadata_digest:
            raise ConfigurationError('web candidate conflicts with stored metadata; use a new identity')
        router.store.save_registry_candidate(candidate)
        candidates[candidate.registry_candidate_id] = candidate
    web_ids = {c.registry_candidate_id for c in request.web_candidates}
    for stage in request.stages:
        options = []
        for spec in router.registry.find(stage.capability) if stage.capability else []:
            try:
                router._require_active_spec(spec)
            except Exception as exc:
                from .errors import AEEPError
                if isinstance(exc, AEEPError):
                    continue
                raise
            options.append(RecommendationOption(candidate_id=spec.id, name=spec.id, source='configured AEEP executor',
                reason='Matches the requested semantic capability; compatibility still needs stack preflight.',
                evidence_basis='configured', readiness='configured', next_action='Compile a GoalSpec and run stack preflight.'))
        tokens = set(' '.join(stage.search_terms).casefold().split())
        for host in request.host_capabilities:
            if tokens.intersection(f'{host.name} {host.description}'.casefold().split()):
                options.append(RecommendationOption(candidate_id='host:' + host.name, name=host.name, source=host.source,
                    reason=f'Host reports relevant capability ({host.availability}); output compatibility needs confirmation.',
                    evidence_basis='host_reported', readiness='host_reported', next_action='Confirm host availability and reviewed mapping.'))
        ranked = sorted(candidates.values(), key=lambda c: (-sum(t in f'{c.name} {c.description}'.casefold() for t in tokens), c.name))
        for candidate in ranked:
            if not any(t in f'{candidate.name} {candidate.description}'.casefold() for t in tokens):
                continue
            supported = candidate.provenance.get('supported_hosts', [])
            unsupported = candidate.provenance.get('unsupported_hosts', [])
            incompatible = isinstance(unsupported, list) and request.host in unsupported
            options.append(RecommendationOption(candidate_id=candidate.registry_candidate_id, name=candidate.name,
                source=str(candidate.provenance.get('catalog') or candidate.source_repository or candidate.remote_endpoint or candidate.adapter_id),
                reason='Description matches stage search terms; ranking is relevance, not measured quality.',
                evidence_basis='web_claim' if candidate.registry_candidate_id in web_ids else 'registry_claim',
                readiness='incompatible' if incompatible else 'setup_required',
                compatibility='incompatible_host' if incompatible else 'supported_host_claim' if isinstance(supported, list) and request.host in supported else 'unknown',
                dependencies=['Unknown until exact package and host requirements are inspected.'],
                next_action='Inspect exact package, dependencies, host support and output contract; review setup.'))
        options.sort(key=lambda o: o.readiness == 'incompatible')
        options = options[:5]
        preferred = next((o.candidate_id for o in options if o.readiness != 'incompatible'), None)
        if stage.preferred_candidate:
            selected = next((o for o in options if o.candidate_id == stage.preferred_candidate and o.readiness != 'incompatible'), None)
            if selected is None or not stage.selection_reason:
                raise ConfigurationError('preferred candidate needs a matching compatible option and selection reason')
            preferred = selected.candidate_id
            selected.reason = 'Host recommendation: ' + stage.selection_reason
        blockers = [] if preferred else ['No compatible candidate found. Refine catalog terms or use host web search and submit sourced candidates.']
        stages.append(StageRecommendation(stage_id=stage.stage_id, purpose=stage.purpose, preferred=preferred, options=options, blockers=blockers))
    status: Literal['recommendation_ready', 'setup_required', 'blocked'] = 'blocked' if any(s.preferred is None for s in stages) else 'setup_required' if any(
        o.readiness == 'setup_required' for s in stages for o in s.options if o.candidate_id == s.preferred) else 'recommendation_ready'
    result = StackRecommendation(recommendation_id=new_id('recommendation'), created_at=utc_now(), host=request.host,
        priorities=list(request.priorities), status=status, stages=stages, search_ids=searches,
        warnings=[*warnings, 'Priorities guide the host comparison. No measured quality, price or privacy is inferred from catalog relevance.',
                  'This recommendation grants no authority. Ready to run requires an executable proposal and current preflight.'])
    AssessmentRepository(router.store).put('stack_recommendation', result.recommendation_id, result)
    return result


def recommendation_tools() -> list[dict[str, Any]]:
    return [dict(name='aeep_discovery_status', description='List configured searchable sources and setup guidance without contacting providers.',
                 schema={'type': 'object', 'properties': {}, 'additionalProperties': False}, annotations={'readOnlyHint': True}),
            dict(name='aeep_stack_recommend', description='Search configured catalogs and compare named options for public task stages. Host capabilities and web findings remain claims. Does not install, grant access or execute.',
                 schema=RecommendationRequest.model_json_schema(), annotations={'readOnlyHint': True})]
