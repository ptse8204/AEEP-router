"""Install and verify the changed wheel with the existing private runtime bridge."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'workflow-telemetry-20261104'
ROOT = HERE.parents[3]
parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
raw = (HERE / 'operation-review.json').read_bytes()
identity = hashlib.sha256(raw).hexdigest()
authority = json.loads((HERE / 'package-authority.json').read_bytes())
assert args.execute_delegated == identity == authority['review_sha256'] and authority['first_attempt']

spec = importlib.util.spec_from_file_location('private_runtime_bridge', PRIOR / 'run-components.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.HERE = HERE
base.SOURCE = ROOT
review, plan = base.verify('package')
assert base.file_digest(HERE / 'operation-review.json') == identity
review['identity'] = identity
result = base.package(review, plan)
print(json.dumps(result))
raise SystemExit(not result['passed'])
