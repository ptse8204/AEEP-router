"""Run an exact reviewed three-route plan through AssessmentService, never bare Runner.

Binding records are supplied by the coordinator after conformance. This module
does not create/review definitions, amend budgets, materialize cases or admit.
"""
import argparse
import asyncio
from pathlib import Path

from aeep.assessment.reporting import paired_interval
from aeep.errors import ConfigurationError

ROOT = Path(__file__).resolve().parents[2]
ROLES = ('normal_host', 'discovery_host', 'discovery_aeep_host')


def require(condition, message):
    if not condition:
        raise ConfigurationError(message)


def checked_path(value):
    path = Path(value).absolute()
    require(path == path.resolve() and path.is_relative_to(ROOT), 'explicit workspace path required')
    require(path.name not in {'auth.json', 'credentials.json', '.env'}, 'secret path forbidden')
    return path


UNSUPPORTED = (
    'original three-way execution unsupported: shared incremental evidence contracts '
    'do not yet bind three roles, equivalent discovery/access policies to actual workers, '
    'and full candidate qualification lineage. No worker, turn, reservation or admission '
    'may start through this report driver.'
)


def validate(service, binding):
    # Deliberately before any record/authority access. Equal declarations are not proof.
    raise ConfigurationError(UNSUPPORTED)


def export(campaign, plan, definition):
    fields = ('trial_id', 'case_id', 'route_id', 'condition', 'repetition', 'phase', 'state', 'ok', 'valid', 'wall_time_ms', 'actual_resources', 'accounting', 'receipt_ids', 'failure_category', 'failure_stage', 'error_type')
    raw = [{k: v for k, v in t.model_dump(mode='json').items() if k in fields} for t in campaign.trials]
    families = {c.case_id: c.template_family for c in plan.suite.cases}
    runs = {(t.case_id, t.route_id): t for t in campaign.trials if t.phase.value == 'holdout'}
    summaries = []
    roles = definition['roles']
    for left, right in [('discovery_aeep_host', 'discovery_host'), ('discovery_host', 'normal_host'), ('discovery_aeep_host', 'normal_host')]:
        differences = {}
        for case in plan.suite.cases:
            a, b = runs.get((case.case_id, roles[left])), runs.get((case.case_id, roles[right]))
            if a and b and a.ok and b.ok and a.valid is True and b.valid is True and a.wall_time_ms is not None and b.wall_time_ms is not None:
                differences[case.case_id] = [b.wall_time_ms - a.wall_time_ms]
        # Six predeclared dimension/contrast tests per budget, two budgets:12.
        estimate, interval = paired_interval(differences, 20, plan.suite.seed, families, alpha=0.05 / 12)
        summaries.append({'left': left, 'right': right, 'distinct_measured_pairs': len(differences), 'wall_time_difference_ms': estimate, 'family_adjusted_interval_ms': interval, 'analysis_scope': 'correct fully measured holdout pairs only; no success/resource benefit gate claimed'})
    return {'trials': raw, 'comparisons': summaries, 'automatic_admission': False, 'full_three_way_value_analysis_complete': False}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binding', required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    # Stop before reading the supplied binding or constructing Router/Service.
    validate(None, {'path': args.binding, 'run': args.run})


if __name__ == '__main__':
    asyncio.run(main())
