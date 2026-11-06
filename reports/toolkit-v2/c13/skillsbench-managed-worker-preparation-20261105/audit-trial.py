"""Join canonical trial, receipt and journal data without disclosing task contents."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.benchmarking import BenchmarkTrial
from aeep.templates import render


def audit(driver, service, plan, pair):
    path = service.directory / plan.plan_id / 'campaign.sqlite3'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        rows = list(connection.execute('SELECT payload_json FROM trials'))
        if len(rows) != 1:
            raise RuntimeError('Expected one canonical trial position')
        trial = BenchmarkTrial.model_validate_json(rows[0][0])
        config = pair.treatment.managed_host_config()
        prompt = dict(plan.suite.cases[0].action.input)
        artifact = config.artifact
        prompt.pop(artifact.input_field)
        prompt.update(input_path='/workspace/' + artifact.input_name, output_path='/workspace/' + artifact.output_name)
        instruction = str(render(config.instructions, {'input': prompt}))
        digest = hashlib.sha256(instruction.encode()).hexdigest()
        evidence = driver.evidence.read_trial(connection, trial, pair, {(trial.case_id, 'skill'): digest},
                                              service.directory / plan.plan_id / 'attempts')
    receipt = evidence['receipt']
    metadata = receipt['metadata']
    score = next((item.quality_score for item in trial.case_validation
                  if item.kind.value == 'callback' and item.trust.value == 'verified'), None)
    capture = evidence['token_capture']
    counts = {name: receipt['actual_resources'][name] for name in capture['known_fields']} if capture else {}
    with service.router.store._lock:
        row = service.router.store._connection.execute(
            'SELECT state,error_code,report_id FROM assessment_jobs WHERE plan_id=?', (plan.plan_id,)).fetchone()
    state, error, report_id = tuple(row)
    result = {key: value for key, value in evidence.items() if key != 'receipt'}
    return result | {
        'plan_id': plan.plan_id, 'plan_digest': content_digest(plan),
        'report_id': report_id, 'job_state': state, 'job_error_code': error,
        'receipt_id': receipt['receipt_id'], 'host_failure_code': metadata.get('host_failure_code'),
        'artifact_transferred': bool(metadata.get('artifact_sha256')),
        'score': score, 'model_turn_count': metadata.get('model_turn_count'),
        'token_counts_provider_reported': counts,
        'agent_wall_seconds': trial.wall_time_ms / 1000 if trial.wall_time_ms is not None else None,
        'grading_wall_seconds': trial.grading_wall_time_ms / 1000 if evidence['independent_grader_observed'] else None,
        'retries': trial.retry_fallback_count,
        'failure_stage': trial.failure_stage, 'failure_category': trial.failure_category,
    }


def passed(record):
    return (record['job_state'] == 'complete' and record['job_error_code'] is None
            and record['score'] in {0, 1} and record['retries'] == 0
            and record['artifact_transferred'] and record['task_prompt_bound']
            and record['canonical_trial_complete'] and record['worker_cleanup_confirmed']
            and record['candidate_loading']['instructions_loaded'] is True
            and record['token_capture']['status'] == 'verified')


def stored_plan(driver, domain):
    return driver.AssessmentPlan.model_validate_json((driver.WORK / f'{domain}-prepared/plan.json').read_bytes())


if __name__ == '__main__':
    import asyncio
    import importlib.util

    path = Path(__file__).resolve().with_name('run-engineering.py')
    spec = importlib.util.spec_from_file_location('prior_approved_skillsbench_run', path)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)

    async def main():
        selected = driver.prepared.pairs(driver.check_review())
        router = driver.Router.from_manifest(driver.MANIFEST)
        try:
            service = driver.AssessmentService(router, driver.CAMPAIGNS)
            evidence = audit(driver, service, stored_plan(driver, 'sales'), selected['sales'][2])
            assert (evidence['job_state'] == 'complete' and evidence['worker_cleanup_confirmed']
                    and evidence['retries'] == 0 and evidence['score'] is None)
            driver.emit('engineering-sales-trial-audit.json', evidence)
            print(json.dumps(evidence))
        finally:
            await router.close()

    asyncio.run(main())
