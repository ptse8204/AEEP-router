"""Prepare and register one React task's exact asset-use determination."""

import argparse
import base64
import importlib.util
import io
import json
import zipfile
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIOR = HERE.parent / 'skillsbench-document-rights-20261106/apply.py'
ORIGINAL = HERE.parent / 'full-stack-20261030/skillsbench-pack.json'
REFERENCE = HERE.parent / 'skillsbench-react-reference-20261106'
ASSET_ROOT = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
TASK = 'react-performance-debugging'
WORK = ROOT / '.aeep' / HERE.name

spec = importlib.util.spec_from_file_location('existing_skillsbench_rights_workflow', PRIOR)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.HERE = HERE


def freeze():
    pack = BenchmarkPack.model_validate(runner.load(ORIGINAL))
    selected = pack.task(TASK)
    task = selected.model_copy(update={
        'assets': tuple(asset for asset in selected.assets if asset.role != 'candidate_skill'),
        'adaptations': ('Original instructions and website files in the managed input archive. '
                        'Bundled skills and hidden simulator stay outside the archive. '
                        'Managed workspace and protected candidate-output carrier are unreviewed.',),
    })
    pack = pack.model_copy(update={'tasks': (task,)})
    payload = task_input(pack, ASSET_ROOT, TASK)
    public = {asset.path: asset.sha256 for asset in task.assets if asset.role in ('instruction', 'input')}
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload['task_archive_b64'], validate=True))) as zipped:
        assert set(zipped.namelist()) == set(public) and len(zipped.namelist()) == 17
    results = [REFERENCE / 'browser-id-continuation/result.json',
               REFERENCE / 'negative-controls/incomplete/result.json',
               REFERENCE / 'negative-controls/destructive/result.json']
    for file, reward in zip(results, (1, 0, 0), strict=True):
        result = runner.load(file)
        assert result['passed'] and result['cleanup_verified']
        assert result['observed']['upstream_binary_reward'] == reward
        assert len(result['observed']['test_statuses']) == 11
    decision = TaskRightsReview(
        source_revision=pack.source.revision, task_id=TASK,
        assets={asset.path: asset.sha256 for asset in task.assets},
        basis=[
            'Original pinned SkillsBench task and in-repository application source under the repository Apache notice.',
            'Exact public archive SHA-256 ' + payload['task_archive_sha256'],
            'Asset-use approval is limited to preparation for a separately approved engineering dispatch to the existing Codex destination.',
            'Verifier, hidden simulator, reference patches, expected outputs and bundled skills stay local.',
        ],
        local_execution_allowed=True, provider_disclosure_allowed=True,
    )
    manifest = HERE / 'react-pack.json'
    draft = HERE / 'proposed-rights.json'
    runner.write(manifest, pack.model_dump(mode='json'))
    runner.write(draft, decision.model_dump(mode='json'))
    review = {
        'scope': 'Register one exact React SkillsBench asset-use determination and verify its local pack binding.',
        'work': str(WORK), 'provider': 'existing Codex destination',
        'no_transfer_or_model_dispatch': True, 'protected_assets_excluded': True,
        'models': 0, 'cash_usd': '0', 'comparisons': 'PAUSED',
        'assets': {str(path): runner.sha(path) for path in
                   (Path(__file__), PRIOR, ORIGINAL, manifest, draft, *results)},
        'tasks': [{
            'task_id': TASK, 'pack': str(manifest), 'decision': str(draft),
            'decision_sha256': content_digest(decision), 'pack_root': str(ASSET_ROOT),
            'public_files': public, 'public_archive_sha256': payload['task_archive_sha256'],
        }],
    }
    runner.write(HERE / 'operation-review.json', review)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--preflight')
    mode.add_argument('--apply-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    path = HERE / 'operation-review.json'
    digest = runner.sha(path)
    assert args.freeze or digest == (args.preflight or args.apply_approved)
    review = runner.load(path)
    assert review['models'] == 0 and review['cash_usd'] == '0' and review['no_transfer_or_model_dispatch']
    if args.apply_approved:
        runner.apply(review, digest)
    else:
        runner.preflight(review)
        print(json.dumps({'passed': True, 'review_sha256': digest, 'public_files': 17, 'models': 0}))
