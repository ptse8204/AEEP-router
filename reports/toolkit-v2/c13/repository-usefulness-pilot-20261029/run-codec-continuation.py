"""Run only unstarted original tasks under the unchanged cumulative approval."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parent = json.loads((HERE / 'operator-approval.json').read_text())
    assert parent['approved'] and parent['review_sha256'] == sha(HERE / 'operation-review.json')
    amendment = json.loads((HERE / 'codec-definition-amendment.json').read_text())
    assert json.loads((HERE / 'codec-component-check.json').read_text())['passed']
    assert json.loads((HERE / 'stopped-accounting-audit.json').read_text())['all_operations_complete']
    save(HERE / 'codec-continuation-started.json', {'parent_review_sha256': parent['review_sha256'],
        'amendment_sha256': sha(HERE / 'codec-definition-amendment.json'),
        'original_cumulative_anchor': amendment['parent_original_cumulative_anchor'],
        'maximum_cumulative_turns': 41, 'no_new_human_approval_claimed': True})
    result = {'parent_review_sha256': parent['review_sha256'], 'components': [], 'all_completed': False}
    try:
        for part in amendment['components']:
            target = Path(part['directory'])
            assert sha(target / 'operation-review.json') == part['review_sha256']
            review = json.loads((target / 'operation-review.json').read_text())
            for path, digest in review['assets'].items():
                assert sha(Path(path)) == digest
            save(target / 'operator-approval.json', {**parent, 'review_sha256': part['review_sha256'],
                'maximum_model_turns': part['maximum_model_turns'], 'maximum_operations': part['maximum_operations'],
                'maximum_reserved_seconds': part['maximum_reserved_seconds'],
                'parent_review_sha256': parent['review_sha256'], 'definition_amendment_sha256': sha(HERE / 'codec-definition-amendment.json'),
                'authority': 'Actual parent human approval plus its delegated routine correction for unstarted tasks. This is not a new human answer or a new allowance.'})
            with (target / 'actual-execution.log').open('x') as stream:
                completed = subprocess.run([sys.executable, str(target / 'run-review.py'), part['review_sha256']], cwd=ROOT,
                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, timeout=12500 if part['mode'] == 'plain' else 5500)
            observed = json.loads((target / 'execution-result.json').read_text())
            result['components'].append({'mode': part['mode'], 'returncode': completed.returncode,
                'result_path': str(target / 'execution-result.json'), 'result_sha256': sha(target / 'execution-result.json'),
                'completed': observed['development_journey_completed']})
            assert completed.returncode == 0 and observed['development_journey_completed'], 'Stop independent dispatch on common execution/evidence uncertainty;do not retry'
        result['all_completed'] = True
    except BaseException as exc:
        result.update(error_type=type(exc).__name__, error_message=str(exc)[:400])
    finally:
        save(HERE / 'codec-continuation-result.json', result)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
