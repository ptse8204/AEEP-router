"""Exercise the actual wrapper with only authored subprocess results in owned temp."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from review_bindings import sha

HERE = Path(__file__).resolve().parent


def main():
    spec = importlib.util.spec_from_file_location('authored_source_dispatch', HERE / 'run_review.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = json.loads((HERE / 'operation-review.json').read_text())
    results = []
    for mode in ('passed', 'known_failure', 'timeout'):
        with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-source-dispatch-') as temporary:
            fixture = Path(temporary)
            out = fixture / 'runtime-execution'
            out.mkdir()
            review = {**original, 'host_canary': str(fixture / 'authored-canary')}
            (fixture / 'operation-review.json').write_text(json.dumps(review))
            digest = sha(fixture / 'operation-review.json')
            (fixture / 'operator-approval.json').write_text(json.dumps({'approved': True,
                'review_sha256': digest, 'source': 'SYNTHETIC FIXTURE,NOT HUMAN AUTHORITY'}))
            calls = []

            def authored_run(argv, **kwargs):
                calls.append(Path(argv[1]).name)
                if mode == 'timeout':
                    raise subprocess.TimeoutExpired(argv, 1)
                if mode == 'known_failure':
                    return subprocess.CompletedProcess(argv, 1)
                (out / 'completion-audit.json').write_text(json.dumps({'batch_completed': True,
                    'physical_receipt_integrity_passed': True, 'all_owned_containers_absent': True,
                    'eligible_cases': [], 'canonical_operations': 0, 'canonical_receipts_reopened': 0,
                    'grant_after': ['SYNTHETIC,NOT A CANONICAL GRANT']}))
                return subprocess.CompletedProcess(argv, 0)

            module.HERE = fixture
            previous = sys.argv
            try:
                sys.argv = ['authored-source-dispatch', digest]
                with patch.object(module.subprocess, 'run', authored_run):
                    try:
                        module.main()
                    except (AssertionError, subprocess.TimeoutExpired):
                        assert mode != 'passed'
                    else:
                        assert mode == 'passed'
            finally:
                sys.argv = previous
            assert calls == (['run.py', 'audit-execution.py'] if mode == 'passed' else ['run.py'])
            assert not (fixture / 'authored-canary').exists()
            value = json.loads((fixture / 'execution-result.json').read_text())
            assert value['batch_completed'] == (mode == 'passed')
            results.append({'mode': mode, 'child_names_not_executed': calls, 'owned_canary_removed': True})
        assert not Path(temporary).exists()
    with (HERE / 'dispatch-check.json').open('x') as output:
        json.dump({'passed': True, 'scenarios': results, 'actual_new_source_execution_or_grant_charge': 0,
            'synthetic_results_are_not_authority_or_benchmark': True}, output, indent=2)
        output.write('\n')
    print(json.dumps({'passed': True, 'authored_scenarios': len(results), 'actual_source_executions': 0}))


if __name__ == '__main__':
    main()
