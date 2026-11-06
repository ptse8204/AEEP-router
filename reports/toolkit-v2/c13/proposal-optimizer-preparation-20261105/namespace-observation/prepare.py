"""Prepare one explicit AFlow repeat against the unchanged runtime and budget."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'namespace-check'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, content):
    with path.open('x') as stream:
        stream.write(content)


old_review = PREVIOUS / 'operation-review.json'
prior = json.loads(old_review.read_bytes())
diagnosis = PREVIOUS / 'diagnosis.json'
observed = json.loads(diagnosis.read_bytes())
assert observed['review_sha256'] == sha(old_review)
assert observed['container_removed'] and observed['failed_line'] == 12
assert prior['maximum_operations'] == 1 and prior['models'] == 0
for path, expected in prior['assets'].items():
    assert sha(path) == expected

new_name = 'aeep-aflow-namespace-observation-20261106'
runner = (PREVIOUS / 'run.py').read_text()
runner = runner.replace('aflow-runtime-namespace-20261105', 'aflow-runtime-namespace-observation-20261106')
runner = runner.replace('aflow_runtime_namespace_check', 'aflow_runtime_namespace_observation')
runner = runner.replace("raw=await executor.execute(ExecutionContext(",
                        "handle=await executor.start(ExecutionContext(")
start = runner.index("            assert raw.exit_code==0")
end = runner.index("        except BaseException", start)
runner = runner[:start] + """            raw=await handle.task
            assert raw.exit_code==0 and raw.status.value=='success'
            assert isinstance(raw.output,dict) and raw.output.get('models')==0
            assert raw.output.get('generated_code_executed') is False
            result.update(observed=raw.output,cleanup_verified=not containers())
            assert result['cleanup_verified']
            assert raw.output['stage']=='complete'
            assert raw.output['optimizer_imported'] and raw.output['actual_graph_parser_passed']
            result['passed']=True
""" + runner[end:]
runner = runner.replace("status=raw.status if raw else 'failed'",
                        "status='success' if result['passed'] else 'failed'")
write(HERE / 'run.py', runner)
argv = [arg.replace(prior['container_name'], new_name)
        .replace(str(PREVIOUS / 'check.py'), str(HERE / 'check.py')) for arg in prior['argv']]
assert len(argv) == len(prior['argv'])
assert sum(a != b for a, b in zip(argv, prior['argv'])) == 2
assert '--network=none' in argv and '--read-only' in argv and '--cap-drop=ALL' in argv
assets = {**prior['assets'], **{str(path): sha(path) for path in (
    old_review, diagnosis, PREVIOUS / 'receipt.json', PREVIOUS / 'ledger.json',
    Path(__file__), HERE / 'check.py', HERE / 'run.py',
)}}
prior.update(scope='One exact offline AFlow namespace diagnosis with an import/parser check only after isolation passes.',
             previous_review_sha256=sha(old_review), previous_charged_operations=1,
             container_name=new_name, argv=argv, assets=assets,
             expires_at=(datetime.now(UTC) + timedelta(days=2)).isoformat())
review = HERE / 'operation-review.json'
write(review, json.dumps(prior, indent=2) + '\n')
print(sha(review))
