"""Apply the approved Sales-only package and grader continuation."""

import argparse
import asyncio
import importlib.util
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def module(name):
    spec = importlib.util.spec_from_file_location('sales_repair_'+name, HERE/(name+'.py'))
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


build = module('build')
verify = module('verify')
parser = argparse.ArgumentParser()
parser.add_argument('--execute-approved', required=True)
args = parser.parse_args()
path = HERE/'operation-review.json'
review = verify.read(path)
identity = verify.sha(path)
approval = verify.read(HERE/'operator-approval.json')
assert args.execute_approved == identity == approval['review_sha256'] and approval['approved'] is True
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
assert shutil.disk_usage(ROOT).free >= 52*1024**3
assert verification_source_digest(ROOT) == review['source_digest']
assert all(verify.sha(file)==digest for file,digest in review['pins'].items())
assert not (HERE/'build-started.json').exists() and not (HERE/'grader-started.json').exists()
assert asyncio.run(build.build(review|{'grant_id':'skillsbench-sales-dependency-build-20261105'},identity))
result = verify.read(HERE/'build-execution/summary.json')
assert result['passed'] and result['accounting_settled'] and set(result['images'])=={'sales'}
case = review['original_case']|{'image_id':result['images']['sales']['image_id']}
print(json.dumps({'review_sha256':identity,'graded_image_id':case['image_id']}))
raise SystemExit(not asyncio.run(verify.verify(review|{
    'grant_id':'skillsbench-sales-dependency-grader-20261105','cases':{'sales':case},
},identity)))
