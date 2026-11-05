"""Run one newly reviewed namespace with the retained Langfuse bridge."""
import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'langfuse-threadpool-correction-20261104'
sys.path.insert(0, str(PRIOR))
spec = importlib.util.spec_from_file_location('reviewed_langfuse_service', PRIOR / 'run-service.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

parser = argparse.ArgumentParser()
parser.add_argument('--execute-approved', required=True)
args = parser.parse_args()
path = HERE / 'operation-review.json'
review = base.load(path)
identity = base.sha(path)
approval = base.load(HERE / 'operator-approval.json')
assert args.execute_approved == identity == approval['review_sha256'] and approval['approved'] is True
base.validate(review)
assert review['project'] == 'aeep-langfuse-merge-capacity-20261104'
base.HERE = HERE
base.PROJECT = review['project']
base.corrected.__globals__['PROJECT'] = base.PROJECT
result = base.execute(review, identity)
print(base.json.dumps(result))
raise SystemExit(not result['passed'])
