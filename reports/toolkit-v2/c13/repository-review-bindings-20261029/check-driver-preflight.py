"""Prove the actual corrected driver stops before Docker on a stale child pin."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

from review_bindings import sha

HERE = Path(__file__).resolve().parent


def main():
    spec = importlib.util.spec_from_file_location('authored_runtime_preflight', HERE / 'run-bundle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = json.loads((HERE / 'runtime-review.json').read_text())
    with tempfile.TemporaryDirectory(prefix='aeep-binding-driver-fixture-') as temporary:
        fixture = Path(temporary)
        review = {**original, 'assets': {str(HERE / 'git_component.py'): '0' * 64}}
        (fixture / 'runtime-review.json').write_text(json.dumps(review))
        (fixture / 'template-operation-review.json').write_bytes((HERE / 'template-operation-review.json').read_bytes())
        (fixture / 'operator-approval.json').write_text(json.dumps({'approved': True,
            'review_sha256': sha(fixture / 'runtime-review.json'),
            'source': 'SYNTHETIC FIXTURE, NOT HUMAN AUTHORITY'}))
        called = []

        def forbidden_inspect(reference):
            called.append(reference)
            raise RuntimeError('Docker must not be reached')

        module.HERE, module.inspect = fixture, forbidden_inspect
        old = sys.argv
        try:
            sys.argv = ['authored-fixture', sha(fixture / 'runtime-review.json')]
            try:
                asyncio.run(module.main())
            except AssertionError as error:
                assert 'file_binding' in str(error)
            else:
                raise AssertionError('Stale runtime review passed driver preflight')
        finally:
            sys.argv = old
        assert not called and not (fixture / 'execution-started.json').exists()
    assert not Path(temporary).exists()
    result = {'passed': True, 'actual_corrected_driver_used': True,
        'stale_nested_pin_rejected_before_Docker_and_marker': True,
        'owned_fixture_removed': True, 'synthetic_approval_not_human_authority': True,
        'actual_download_build_install_container_model_or_grant_charge': False}
    with (HERE / 'driver-preflight-check.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
