"""Check the changed guide and current documentation with the retained tools."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = HERE.parents[2] / 'langfuse-service-20261104' / 'run-docs.py'
spec = importlib.util.spec_from_file_location('retained_docs_runner', source)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.HERE = HERE
parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
path = HERE / 'docs-review.json'
review = runner.load(path)
authority = runner.load(HERE / 'docs-authority.json')
digest = runner.sha(path)
assert args.execute_delegated == digest == authority['review_sha256']
assert authority['first_attempt'] is True
result = runner.execute(review, digest)
print(json.dumps({k: v for k, v in result.items() if k != 'input_hashes'}))
raise SystemExit(not result['passed'])
