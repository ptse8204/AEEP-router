"""Score frozen selection decisions without changing routes or admission authority."""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from .models import ContractModel, Digest, Identifier, Measure

if TYPE_CHECKING:
    from aeep.models import RouteDecision


class SelectionCase(ContractModel):
    case_id: Identifier
    task_sha256: Digest
    family: Identifier
    eligible: tuple[Identifier, ...]
    demonstrated_useful: tuple[Identifier, ...]
    eligibility_ref: Digest
    prior_value_ref: Digest | None = None
    value_known: bool

    @model_validator(mode='after')
    def applicable_value(self) -> SelectionCase:
        if (len(set(self.eligible)) != len(self.eligible)
                or len(set(self.demonstrated_useful)) != len(self.demonstrated_useful)
                or not set(self.demonstrated_useful) <= set(self.eligible)):
            raise ValueError('usefulness must refer to distinct eligible capabilities')
        if (self.demonstrated_useful and not self.value_known) or (self.value_known and self.prior_value_ref is None):
            raise ValueError('known value needs independently established pre-task evidence')
        return self


class SelectionDecision(ContractModel):
    policy: Identifier
    case_id: Identifier
    selected: Identifier | None
    decision_ref: Digest
    decision_wall_seconds: Measure | None = None
    task_verified: bool | None = None
    verification_ref: Digest | None = None

    @model_validator(mode='after')
    def verified_outcome(self) -> SelectionDecision:
        if self.task_verified is not None and self.verification_ref is None:
            raise ValueError('task outcomes need independent grading references')
        return self


class SelectionPolicy(ContractModel):
    definition_ref: Digest
    inventory_sha256: Digest
    shared_environment_sha256: Digest
    authority_sha256: Digest
    model_settings_sha256: Digest


class SelectionEvaluation(ContractModel):
    schema_version: Literal['aeep.toolkit.selection-evaluation.v1'] = 'aeep.toolkit.selection-evaluation.v1'
    evidence_kind: Literal['synthetic', 'replay', 'live']
    plan_ref: Digest
    inventory: dict[Identifier, Digest]
    shared_environment_sha256: Digest
    authority_sha256: Digest
    model_settings_sha256: Digest
    # These are frozen policy definitions, never held-out outcomes or a selector input.
    policies: dict[Identifier, SelectionPolicy]
    cases: tuple[SelectionCase, ...] = Field(min_length=1, max_length=10000)
    decisions: tuple[SelectionDecision, ...] = Field(max_length=50000)

    @model_validator(mode='after')
    def complete_matrix(self) -> SelectionEvaluation:
        if len(self.policies) < 2 or len(self.policies) > 8:
            raise ValueError('selection comparison requires two to eight frozen policies')
        from aeep.assessment.models import content_digest

        for policy in self.policies.values():
            if (policy.inventory_sha256 != content_digest(self.inventory)
                    or policy.shared_environment_sha256 != self.shared_environment_sha256
                    or policy.authority_sha256 != self.authority_sha256
                    or policy.model_settings_sha256 != self.model_settings_sha256):
                raise ValueError('selection policies must share exact inventory, environment, model and authority')
        ids = [case.case_id for case in self.cases]
        if len(set(ids)) != len(ids) or len({case.task_sha256 for case in self.cases}) != len(ids):
            raise ValueError('selection cases must be distinct; repetitions are not independent tasks')
        if any(not set(case.eligible) <= self.inventory.keys() for case in self.cases):
            raise ValueError('eligibility cannot invent capabilities outside the shared inventory')
        keys = [(item.policy, item.case_id) for item in self.decisions]
        if len(set(keys)) != len(keys) or set(keys) != {(policy, case) for policy in self.policies for case in ids}:
            raise ValueError('every policy must have exactly one decision for every frozen case')
        if len({decision.decision_ref for decision in self.decisions}) != len(self.decisions):
            raise ValueError('selection decision references cannot be reused')
        return self


def from_route_decision(decision: RouteDecision, *, policy: str, case: SelectionCase,
                        baseline_executor_id: str, capability_by_executor: dict[str, str]) -> SelectionDecision:
    """Record an actual AEEP decision; invoking the selected capability is separate."""
    from aeep.assessment.models import content_digest
    from aeep.models import RouteDecision

    decision = RouteDecision.model_validate(decision)
    if content_digest(decision.action.input) != case.task_sha256:
        raise ValueError('selection decision does not match the frozen task input')
    selected = decision.selected_executor_id
    if selected is None or selected == baseline_executor_id:
        capability = None
    else:
        capability = capability_by_executor[selected]
    return SelectionDecision(policy=policy, case_id=case.case_id, selected=capability,
        decision_ref=content_digest(decision), decision_wall_seconds=decision.routing_overhead_ms / 1000)


def summarize_selection(evaluation: SelectionEvaluation) -> dict[str, Any]:
    """Descriptive scoring; reference authentication and scientific admission stay upstream."""
    cases = {case.case_id: case for case in evaluation.cases}
    summaries = {}
    for policy in evaluation.policies:
        counts: Counter[str] = Counter()
        measured = []
        families: dict[str, Counter[str]] = {}
        for decision in (item for item in evaluation.decisions if item.policy == policy):
            case = cases[decision.case_id]
            result = Counter(total=1)
            if decision.selected is None:
                result['abstentions'] += 1
                if case.demonstrated_useful:
                    result['missed_applicable_value'] += 1
                elif case.value_known:
                    result['correct_abstentions'] += 1
            elif decision.selected not in case.eligible:
                result['ineligible_selections'] += 1
            elif decision.selected in case.demonstrated_useful:
                result['useful_selections'] += 1
            elif case.value_known:
                result['unnecessary_selections'] += 1
            else:
                result['value_unknown_selections'] += 1
            if not case.value_known:
                result['unknown_value_cases'] += 1
            if decision.task_verified is None:
                result['ungraded_tasks'] += 1
            else:
                result['graded_tasks'] += 1
                result['verified_successes'] += int(decision.task_verified)
            if decision.decision_wall_seconds is not None:
                measured.append(decision.decision_wall_seconds)
            counts.update(result)
            families.setdefault(case.family, Counter()).update(result)
        summaries[policy] = {'counts': dict(counts), 'families': {key: dict(value) for key, value in families.items()},
            'decision_time': {'measured': len(measured), 'missing': len(cases) - len(measured),
                'observed_total_seconds': sum(measured) if measured else None}}
    from itertools import combinations

    decisions = {(item.policy, item.case_id): item for item in evaluation.decisions}
    comparisons = []
    for left, right in combinations(evaluation.policies, 2):
        paired = [(decisions[left, case], decisions[right, case]) for case in cases]
        graded = [(a, b) for a, b in paired if a.task_verified is not None and b.task_verified is not None]
        timed = [(a.decision_wall_seconds, b.decision_wall_seconds) for a, b in paired
                 if a.decision_wall_seconds is not None and b.decision_wall_seconds is not None]
        comparisons.append({'left': left, 'right': right, 'expected_pairs': len(cases),
            'graded_pairs': len(graded),
            'success_rate_left_minus_right': sum(int(a.task_verified is True) - int(b.task_verified is True)
                for a, b in graded) / len(graded) if graded else None,
            'decision_time_pairs': len(timed),
            'mean_decision_seconds_left_minus_right': sum(a - b for a, b in timed) / len(timed) if timed else None,
            'confidence_interval': None})
    return {'schema_version': 'aeep.toolkit.selection-summary.v1', 'evidence_kind': evaluation.evidence_kind,
        'outcome': 'NOT_ASSESSED', 'policies': summaries, 'admission_changed': False,
        'comparisons': comparisons,
        'inspection_references': [decision.model_dump(mode='json') for decision in evaluation.decisions],
        'limitations': ['Describes supplied decisions; references and equal-environment assertions are not authenticated by this command.',
            'Usefulness labels must come from independent evidence frozen before these task outcomes; unknown value is not zero.',
            'Decision correctness and independently graded task success are separate results. No significance or savings claim is made.',
            'Infrastructure acceptance and resource budgets are separate from this evaluation.']}
