"""Reuse completed reproduction drivers and add the existing exact budget guard."""
import base64
import hashlib
import json
from pathlib import Path

from aeep.assessment.repository_suites import archive_files, pack_files

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def main():
    assert not (HERE / 'approval-bundle.json').exists()
    assert not (HERE / 'execution-started.json').exists()
    previous = HERE.parent / 'repository-workload-batch-20261022'
    out = HERE / 'runtime-execution'
    out.mkdir(exist_ok=True)
    for name in ('run.py', 'audit-execution.py', 'classify.py'):
        text = (previous / 'runtime-execution' / name).read_text()
        if name == 'run.py':
            anchor = "        grant = repo.current_grant('onboarding')"
            addition = """        import importlib.util
        budget_spec = importlib.util.spec_from_file_location('exact_review_budget', HERE.parent / 'review-budget.py')
        budget = importlib.util.module_from_spec(budget_spec); budget_spec.loader.exec_module(budget)
        envelope = json.loads((HERE.parent / 'approval-bundle.json').read_text())
        initial = json.loads((HERE.parent / 'build-result.json').read_text())['grant_before']
        budget.install(repo, router.store._connection, initial, envelope)
"""
            assert text.count(anchor) == 1
            text = text.replace(anchor, addition + anchor)
        (out / name).write_text(text)
    text = (previous / 'run-bundle.py').read_text()
    anchor = "        grant = repo.current_grant('onboarding')"
    addition = """        import importlib.util
        budget_spec = importlib.util.spec_from_file_location('exact_review_budget', HERE / 'review-budget.py')
        budget = importlib.util.module_from_spec(budget_spec); budget_spec.loader.exec_module(budget)
        budget.install(repo, router.store._connection, build['grant_before'], bundle)
"""
    assert text.count(anchor) == 1
    (HERE / 'run-bundle.py').write_text(text.replace(anchor, addition + anchor))
    text = (previous / 'derive-execution.py').read_text().replace('repository-pydantic-django-runtime-20261022', 'repository-independent-runtime-20261024').replace('Twenty-two provisional tasks', 'Five provisional tasks').replace('at most ninety-seven offline calls.', 'at most thirteen offline calls.').replace('seed=67', 'seed=79')
    (HERE / 'derive-execution.py').write_text(text)
    (HERE / 'review-budget.py').write_bytes((HERE.parent / 'repository-task-delivery-20261023/review-budget.py').read_bytes())
    current = json.loads((HERE.parent / 'repository-task-delivery-20261023/grader-probe-definitions.json').read_text())
    recipe = next(v['document'] for v in current['documents'].values() if v['kind'] == 'recipe')
    parent = json.loads((previous / 'runtime-execution/parent-runtime-review.json').read_text())
    parent.update(source_digest=current['source_digest'], recipe=recipe, request=current['request'], documents=current['documents'], authorization_digest=current['amendment']['authorization_digest'], host_canary='.aeep/repository-independent-control-20261024/host-canary')
    versions = {p['project']: p['version'] for p in json.loads((HERE / 'runtime-support-review.json').read_text())['pins']}
    probes = json.loads((HERE.parent / 'repository-task-delivery-20261023/grader-probes.json').read_text())
    old_canary = current['canary'].encode()
    for probe in probes:
        files = archive_files(base64.b64decode(probe['payload']['archive']))
        files = {name: data.replace(old_canary, str(ROOT / parent['host_canary']).encode()) for name, data in files.items()}
        if probe['name'] == 'boundary':
            name = probe['expected_node'].split('::')[0]
            files[name] += ('\n\ndef test_independent_runtime_support_versions():\n    import importlib.metadata\n    expected = ' + repr(versions) + '\n    for project, version in expected.items():\n        assert importlib.metadata.version(project) == version\n    import sqlalchemy, msgspec, arrow, httpx_ws, requests_mock\n    assert sqlalchemy.__version__ == "2.0.44"\n    assert msgspec.json.decode(b"{\\\"number\\\": 3}")["number"] == 3\n    assert arrow.get("2025-01-01").year == 2025\n').encode()
        archive = pack_files(files)
        probe['payload']['archive'] = base64.b64encode(archive).decode()
        probe['payload']['archive_sha256'] = hashlib.sha256(archive).hexdigest()
        probe['archive_sha256'] = probe['payload']['archive_sha256']
        probe['payload_sha256'] = hashlib.sha256(json.dumps(probe['payload'], separators=(',', ':')).encode()).hexdigest()
    parent['probes'] = probes
    parent['current_probe_extension'] = 'All16 exact optional support versions plus SQLAlchemy/msgspec/Arrow imports; three fresh boundary/state probes mandatory. No prior conformance transfers.'
    (HERE / 'observer-envelope.json').write_text(json.dumps(parent, indent=2) + '\n')
    canary = ROOT / parent['host_canary']
    canary.parent.mkdir(exist_ok=False)
    assert not canary.exists()
    print(json.dumps({'drivers': 5, 'probes': len(probes), 'new_support_versions': len(versions), 'hard_budget_guard': True, 'source_executions': 0, 'models': 0, 'builds': 0}))


if __name__ == '__main__':
    main()
