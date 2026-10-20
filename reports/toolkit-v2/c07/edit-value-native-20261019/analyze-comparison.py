"""Read terminal canonical evidence; export all four arms without new dispatch."""
import asyncio
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from statistics import mean, median
import sys

from aeep.assessment.models import AssessmentOperationLedger, AssessmentReport, content_digest
from aeep.assessment.reporting import native_measurements
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkCampaignReport
from aeep.models import ExecutionReceipt
from aeep.router import Router
from aeep_toolkit.managed import AEEPAssessmentAdapter
from aeep_toolkit.models import SourcePin

OUT = Path(__file__).parent
ROOT = OUT.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def distribution(values):
    known = [v for v in values if v is not None]
    return {'known': len(known), 'assigned': len(values),
            'known_subtotal': sum(known) if known else None,
            'complete_total': sum(known) if known and len(known) == len(values) else None,
            'mean': mean(known) if known else None, 'median': median(known) if known else None}


def collect_scope(value, identities):
    """Only explicit lifecycle identities; skip embedded definition bundles."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'plan_id', 'request_id', 'operation_id', 'training_plan_id',
                       'origin_plan_id', 'predecessor_plan_id', 'build_operation_id'} and isinstance(item, str):
                identities.add(item)
            elif key == 'request_ids' and isinstance(item, list):
                identities.update(x for x in item if isinstance(x, str))
            elif key not in {'definitions', 'documents', 'plan', 'training_plan'}:
                collect_scope(item, identities)
    elif isinstance(value, list):
        for item in value:
            collect_scope(item, identities)


async def main():
    terminal = read(OUT / 'value-result.json')
    assert terminal['proxy_restored'] and terminal['source_unchanged']
    assert terminal['status']['state'] == 'complete' and terminal['status']['error_code'] is None
    assert read(OUT / 'report/operation.json')['state'] == 'exported'
    review = read(OUT / 'analysis-plan.json')
    assert review['runner_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    try:
        adapter = AEEPAssessmentAdapter(service, terminal['plan_id'], SourcePin.model_validate(read(OUT / 'source-pin.json')))
        primary = adapter.normalize(terminal['report_id'])
        assert not adapter.details['normalization_gaps']
        assert not any(adapter.details[key] for key in ('missing_trial_positions', 'unexpected_trial_positions', 'duplicate_trial_positions'))
        report = AssessmentReport.model_validate(repo.get('report', terminal['report_id']))
        campaign = BenchmarkCampaignReport.model_validate(repo.get('campaign', report.campaign_digest))
        plan = adapter.plan
        assert content_digest(plan) == review['plan_digest']
        specs = {spec.id: spec for spec in adapter.mapping.subjects}
        arms = {plan.baseline_id: 'ordinary', plan.candidate_id: 'optional_candidate',
                plan.comparison.experiment.higher_compute.executor_id: 'higher_compute',
                plan.comparison.experiment.reusable_tool.executor_id: 'reusable_tool'}
        assert set(arms) == set(specs) and len(arms) == 4
        cases = {case.case_id: case for case in plan.suite.cases}
        path = service.directory / plan.plan_id / 'campaign.sqlite3'
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
            receipts = {r[0]: (r[1], ExecutionReceipt.model_validate_json(r[2])) for r in
                        conn.execute('SELECT receipt_id,trial_id,payload_json FROM trial_receipts')}
            stores = dict(conn.execute('SELECT trial_id,database_path FROM trial_stores'))
        records = []
        original_mapping = adapter.mapping
        for trial in campaign.trials:
            assert trial.route_id in arms and len(trial.receipt_ids) == 1
            trial_id, receipt = receipts[trial.receipt_ids[0]]
            assert trial_id == trial.trial_id and receipt.executor_id == trial.route_id
            original = Path(stores[trial.trial_id]).resolve(strict=True)
            assert original.parent == service.directory / plan.plan_id / 'attempts'
            with sqlite3.connect(original.as_uri() + '?mode=ro', uri=True) as conn:
                row = conn.execute('SELECT payload_json FROM receipts WHERE receipt_id=?', (receipt.receipt_id,)).fetchone()
            assert row is not None and content_digest(ExecutionReceipt.model_validate_json(row[0])) == content_digest(receipt)
            # Reuse the existing receipt verifier with each exact auxiliary spec.
            # This is local normalization only; no canonical mapping is changed.
            adapter.mapping = original_mapping.model_copy(update={'baseline': specs[trial.route_id]})
            run = adapter._run(trial, receipt)
            case = cases[trial.case_id]
            records.append({'trial_id': trial.trial_id, 'case_id': trial.case_id,
                'arm': arms[trial.route_id], 'phase': trial.phase.value,
                'family': case.template_family, 'variation': case.variation,
                'condition': trial.condition.value, 'repetition': trial.repetition,
                'status': run.status, 'verification': run.verification,
                'wall_seconds': run.agent_wall_seconds, 'grading_seconds': run.verification_wall_seconds,
                'reported_tokens': run.tokens.model_dump(mode='json') if run.tokens else None,
                'token_provenance': [u.evidence.model_dump(mode='json') for u in receipt.accounting.model_usage],
                'strict_native_measurements': native_measurements(trial),
                'discovery': trial.capability_discovery, 'receipt_ref': content_digest(receipt),
                'trial_ref': content_digest(trial), 'worker_ref': run.worker_sha256,
                'prompt_ref': run.prompt_sha256, 'model': run.model, 'host_version': run.host_version,
                'effort': run.effort})
        adapter.mapping = original_mapping
        assert len(records) == adapter.details['expected_trial_positions'] == 564
        groups = defaultdict(list)
        for r in records:
            groups[r['condition'], r['phase'], r['family'], r['arm']].append(r)
        summaries = []
        for (condition, phase, family, arm), group in sorted(groups.items()):
            summaries.append({'condition': condition, 'phase': phase, 'family': family, 'arm': arm,
                'assigned': len(group), 'verification': dict(Counter(r['verification'] for r in group)),
                'status': dict(Counter(r['status'] for r in group)),
                'wall_seconds': distribution([r['wall_seconds'] for r in group]),
                'reported_input_tokens': distribution([(r['reported_tokens'] or {}).get('input_tokens') for r in group]),
                'reported_output_tokens': distribution([(r['reported_tokens'] or {}).get('output_tokens') for r in group]),
                'trusted_input_tokens': distribution([r['strict_native_measurements'].get('model.openai.gpt-6-astra.subscription.input_tokens') for r in group]),
                'trusted_output_tokens': distribution([r['strict_native_measurements'].get('model.openai.gpt-6-astra.subscription.output_tokens') for r in group]),
                'candidate_invocation': dict(Counter(str((r['discovery'] or {}).get('invoked')) for r in group))})
        canonical_ledger = AssessmentOperationLedger.model_validate(repo.get('operation_ledger', report.operation_ledger_digest))
        identities = {o.operation_id for o in canonical_ledger.operations}
        scopes = []
        folders = sorted(OUT.parent.glob('edit*')) + [ROOT / 'reports/toolkit-v2/integration-completion/worker-readiness-repair-20261019']
        for folder in folders:
            for document in sorted(folder.glob('*.json')):
                if document.name.startswith(('analysis', 'all-four', 'study-accounting', 'accounting-scope')):
                    continue
                found = set()
                collect_scope(read(document), found)
                if found:
                    scopes.append({'path': str(document.relative_to(ROOT)),
                        'sha256': hashlib.sha256(document.read_bytes()).hexdigest(), 'identities': sorted(found)})
                    identities.update(found)
        ledger = repo.operation_ledger(plan.plan_id, sorted(identities), sorted(identities))
        assert len({o.operation_id for o in ledger.operations}) == len(ledger.operations)
        assert {o.operation_id for o in canonical_ledger.operations} <= {o.operation_id for o in ledger.operations}
        for op in ledger.operations:
            grant = router.store._connection.execute('SELECT grant_id FROM assessment_operations WHERE id=?', (op.operation_id,)).fetchone()
            assert grant is not None and grant[0] == plan.authorization_id
        cost_groups = defaultdict(list)
        for op in ledger.operations:
            cost_groups[op.stage].append(op)
        cost_summary = {stage: {'operations': len(ops),
            'charged_operation_seconds': distribution([o.elapsed_seconds for o in ops])}
            for stage, ops in sorted(cost_groups.items())}
        diagnosis = read(OUT.parent / 'edit-reusable-20261019/copy-permission-diagnosis.json')
        accounting = {'scope': 'Editing study and linked canonical predecessors/preparation, not all repository history',
            'ledger_ref': content_digest(ledger), 'operations': len(ledger.operations),
            'unresolved_operations': sum(o.elapsed_seconds is None for o in ledger.operations),
            'charged_operation_seconds': distribution([o.elapsed_seconds for o in ledger.operations]),
            'by_stage': cost_summary, 'unreserved_observation': diagnosis['initial_unreserved_observation'],
            'limits': ['Operation durations overlap; their sum is not elapsed study wall time.',
                       'Subscription capacity and the zero cash ceiling are not dollar savings.',
                       'Missing or self-asserted resource values are not independently verified costs.',
                       'Software engineering and whole-host energy/CPU/memory costs are not completely measured.']}
        output = {'plan_id': plan.plan_id, 'report_id': report.report_id, 'source_digest': terminal['source_digest'],
            'canonical_outcome': report.outcome, 'canonical_utility': report.utility_evidence,
            'canonical_conditions': report.condition_comparisons, 'normalization_gaps': 0,
            'primary_trials': len(primary.runs), 'all_four_trials': len(records),
            'family_phase_arm_summaries': summaries, 'records': records,
            'accounting_summary': accounting, 'admission': False,
            'limits': review['limits']}
        write(OUT / 'all-four-evidence.json', output)
        write(OUT / 'study-accounting-ledger.json', ledger.model_dump(mode='json'))
        write(OUT / 'accounting-scope.json', scopes)
        write(OUT / 'study-accounting-summary.json', accounting)
        print(json.dumps({k: output[k] for k in ('report_id', 'canonical_outcome', 'normalization_gaps', 'primary_trials', 'all_four_trials', 'admission')}))
    finally:
        await router.close()


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-check']:
        assert distribution([None, 2, 4]) == {'known': 2, 'assigned': 3, 'known_subtotal': 6, 'complete_total': None, 'mean': 3, 'median': 3}
        assert distribution([])['complete_total'] is None
        found = set()
        collect_scope({'request_ids': ['a'], 'request': {'request_id': 'b'}, 'definitions': {'plan_id': 'unrelated'}}, found)
        assert found == {'a', 'b'}
        print('Three pure analysis self-checks passed; no assessment or receipt opened.')
    else:
        assert not sys.argv[1:]
        asyncio.run(main())
