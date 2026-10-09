"""Read-only resolution of controlled fixture artifacts, receipts, events and analysis."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from aeep.assessment.models import (
    AssessmentOperationLedger,
    AssessmentPlan,
    RecipeDefinition,
    content_digest,
)
from aeep.assessment.reporting import fit_report
from aeep.benchmarking import BenchmarkCampaignReport
from aeep.models import ExecutionReceipt, RouteDecision
from aeep_toolkit.cli import read_bytes, read_json
from aeep_toolkit.models import EvidenceBundle


def verify(output):
    output = output.resolve(strict=True)
    result = read_json(output/'result.json')
    bundle = EvidenceBundle.model_validate(read_json(output/'toolkit-evidence.json'))
    summary = read_json(output/'summary.json')
    database = output/'receipts.sqlite3'
    if database.is_symlink() or not database.is_file() or database.stat().st_nlink != 1:
        raise ValueError('missing or linked receipt database')
    wal = database.with_name(database.name+'-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('close the receipt writer before verification')
    connection = sqlite3.connect('file:'+quote(str(database),safe='/')+'?mode=ro&immutable=1',uri=True)
    def record(kind, reference):
        rows = connection.execute('SELECT digest,payload_json FROM assessment_records WHERE kind=? AND (id=? OR digest=?)',
                                  (kind,reference,reference)).fetchall()
        if len(rows) != 1:
            raise ValueError('missing or ambiguous canonical record')
        digest, raw = rows[0]
        value = json.loads(raw)
        if content_digest(value) != digest:
            raise ValueError('canonical record digest mismatch')
        return value
    try:
        analysis_facts = summary['reviewed_analysis']
        if record('toolkit_controlled_bundle',analysis_facts['bundle_ref']) != {'facts':bundle.model_dump(mode='json')}:
            raise ValueError('bundle changed')
        definition = record('toolkit_controlled_definition',result['definition_ref'])
        review = definition['facts'].get('review')
        review_sha = definition['facts'].get('review_sha256')
        expected_retention = review['inputs']['retain_outputs'] if review is not None else True
        if result.get('outputs_retained',True) is not expected_retention:
            raise ValueError('output retention differs from reviewed plan')
        if review is not None and hashlib.sha256(json.dumps(review,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest() != review_sha:
            raise ValueError('evaluation review binding differs')
        if bundle.adapter.implementation_sha256 != (review_sha or content_digest(definition)):
            raise ValueError('adapter binding differs')
        plan = AssessmentPlan.model_validate(record('toolkit_analysis_plan',bundle.runs[0].plan_ref))
        if record('toolkit_controlled_summary',plan.plan_id) != {'facts':summary}:
            raise ValueError('summary changed')
        recipe = RecipeDefinition.model_validate(record('recipe',plan.recipe_digest))
        environment = record('environment',plan.environment_digest)
        if result['environment'] != environment:
            raise ValueError('environment binding differs')
        campaign = BenchmarkCampaignReport.model_validate(record('toolkit_controlled_campaign',analysis_facts['campaign_ref']))
        expected = {(c.case_id,arm) for c in plan.suite.cases for arm in ('control','treatment')}
        if len(result['trials']) != len(expected) or {(r['case'],r['arm']) for r in result['trials']} != expected:
            raise ValueError('missing or duplicate expected trials')
        by_operation = {trial.trial_id:trial for trial in campaign.trials}
        by_receipt = {run.run_id:run for run in bundle.runs}
        if len(by_operation) != len(expected) or len(by_receipt) != len(expected):
            raise ValueError('analysis and bundle positions differ')
        operations = []
        for row in result['trials']:
            operation = row['operation_id']
            if record('toolkit_controlled_result',operation) != {'facts':row}:
                raise ValueError('trial result changed')
            receipt = ExecutionReceipt.model_validate(record('toolkit_controlled_receipt',row['receipt_ref']))
            saved = connection.execute('SELECT payload_json FROM receipts WHERE receipt_id=?',(receipt.receipt_id,)).fetchone()
            if not saved or content_digest(json.loads(saved[0])) != row['receipt_ref']:
                raise ValueError('receipt changed')
            decision = RouteDecision.model_validate(record('toolkit_controlled_decision',receipt.metadata['decision_ref']))
            saved = connection.execute('SELECT payload_json FROM decisions WHERE decision_id=?',(decision.decision_id,)).fetchone()
            if (not saved or content_digest(json.loads(saved[0])) != receipt.metadata['decision_ref']
                    or decision.action.action_id != receipt.action_id or decision.selected_executor_id != receipt.executor_id
                    or decision.action.input != {'__aeep_redacted__':True}):
                raise ValueError('decision changed or contains task payload')
            for event in receipt.metadata['execution_evidence']['events']:
                if record('execution_event',f"{event['journal_id']}:{event['sequence']}") != event:
                    raise ValueError('execution event changed')
            run = by_receipt[receipt.receipt_id]
            if run.receipt_refs != (row['receipt_ref'],) or run.evidence_kind != 'synthetic' or run.plan_ref != content_digest(plan):
                raise ValueError('normalized receipt binding differs')
            verification = record('toolkit_controlled_verification',run.verification_ref)['facts']
            relative = Path(verification['row']['artifact'])/'outputs/output.txt'
            artifact = output/'upstream'/relative
            if relative.is_absolute() or '..' in relative.parts or artifact.resolve() != artifact:
                raise ValueError('unsafe artifact path')
            if verification['output_sha256'] != row['output_sha256']:
                raise ValueError('recorded graded digest differs from worker result')
            if result.get('outputs_retained',True) and hashlib.sha256(read_bytes(artifact)).hexdigest() != row['output_sha256']:
                raise ValueError('graded artifact changed')
            trial = by_operation[operation]
            if trial.receipt_ids != [receipt.receipt_id] or trial.valid != verification['row']['verified']:
                raise ValueError('campaign grading or receipts differ')
            operations.append(record('operation_measurement',operation))
        ledger = AssessmentOperationLedger(plan_id=plan.plan_id,operations=sorted(operations,key=lambda o:o['operation_id']))
        if ledger.model_dump(mode='json') != result['ledger']:
            raise ValueError('operation accounting changed')
        analysis = fit_report(plan,recipe,campaign,ledger=ledger)
        saved_analysis = record('toolkit_controlled_analysis',analysis_facts['analysis_ref'])
        # AssessmentReport identity/timestamp are generated during each calculation.
        for key in ('report_id','created_at'):
            saved_analysis.pop(key,None)
        recalculated = analysis.model_dump(mode='json')
        for key in ('report_id','created_at'):
            recalculated.pop(key,None)
        if saved_analysis != recalculated or analysis.qualification_passed or summary['outcome'] != 'NOT_ASSESSED':
            raise ValueError('analysis changed or fixture claims qualification')
        return {'verified_trials':len(expected),'unique_receipts':len(by_receipt),'analysis_outcome':analysis.outcome,
                'evidence_kind':'synthetic','live_benefit':'not_assessed',
                'outputs_retained':result.get('outputs_retained',True),
                'grading_replay':'artifact integrity checked' if result.get('outputs_retained',True) else 'canonical grading records only; output contents not retained'}
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    print(json.dumps(verify(parser.parse_args().output),indent=2))
