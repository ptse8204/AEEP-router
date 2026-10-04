"""Read-only, content-free progress for the fixed C qualification campaign."""
import json
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = 'plan_143001e5f4be4fd9b17f78d797340b70'
CANONICAL = ROOT / '.aeep/live-review-v3/aeep.sqlite3'
CAMPAIGN = ROOT / '.aeep/live-review-v3/.aeep/assessments' / PLAN / 'campaign.sqlite3'


def connect(path):
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


with connect(CANONICAL) as canonical:
    plan = json.loads(canonical.execute(
        "SELECT payload_json FROM assessment_records WHERE kind='plan' AND id=?", (PLAN,)
    ).fetchone()[0])
    split_by_case = {case['case_id']: case['split'] for case in plan['suite']['cases']}
    jobs = [dict(zip(('id', 'state', 'report_id', 'error_code'), row)) for row in canonical.execute(
        'SELECT id,state,report_id,error_code FROM assessment_jobs WHERE plan_id=?', (PLAN,)
    )]
    usage = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), canonical.execute(
        "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'"
    ).fetchone()))
counts = Counter()
with connect(CAMPAIGN) as campaign:
    for state, case, valid, failed, error, status in campaign.execute(
        "SELECT state,json_extract(payload_json,'$.case_id'),json_extract(payload_json,'$.valid'),"
        "json_extract(payload_json,'$.correctness_failed'),json_extract(payload_json,'$.error_type'),json_extract(payload_json,'$.status') FROM trials"
    ):
        result = 'running' if state != 'complete' else 'passed' if valid and not failed else error or ('correctness_failed' if failed else status or 'invalid')
        counts[(split_by_case[case], result)] += 1
print(json.dumps({'observed_at': datetime.now(timezone.utc).isoformat(), 'jobs': jobs,
                  'counts': [{'split': split, 'result': result, 'count': count}
                             for (split, result), count in sorted(counts.items())],
                  'grant_usage': usage,
                  'free_gib': round(shutil.disk_usage(ROOT).free / 1024**3, 2)}, sort_keys=True))
