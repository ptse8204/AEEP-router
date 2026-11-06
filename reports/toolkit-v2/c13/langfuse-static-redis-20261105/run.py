"""Execute one exact Langfuse repeat with private Redis name resolution."""

import argparse
import importlib.util
import sys
from pathlib import Path

from redis_adaptation import PROJECT, apply

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'langfuse-threadpool-correction-20261104'
sys.path.insert(0, str(HERE.parent/'langfuse-host-sandbox-20261105'))
from heap_adaptation import apply as apply_heap  # noqa: E402

sys.path.insert(0, str(PRIOR))
spec = importlib.util.spec_from_file_location('reviewed_langfuse_service', PRIOR/'run-service.py')
assert spec and spec.loader
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

parser = argparse.ArgumentParser()
parser.add_argument('--execute-approved', required=True)
args = parser.parse_args()
path = HERE/'operation-review.json'
review = base.load(path)
identity = base.sha(path)
approval = base.load(HERE/'operator-approval.json')
assert args.execute_approved == identity == approval['review_sha256'] and approval['approved'] is True
base.validate(review)
assert review['project'] == PROJECT
base.HERE = HERE
base.PROJECT = PROJECT
adapt_namespace = base.corrected
adapt_namespace.__globals__['PROJECT'] = PROJECT


def corrected(config, work):
    return apply(apply_heap(adapt_namespace(config, work)))


base.corrected = corrected
result = base.execute(review, identity)
print(base.json.dumps(result))
raise SystemExit(not result['passed'])
