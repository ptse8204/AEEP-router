"""Register the two exact local SkillsBench rights records without dispatch."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.workflow_preparation import TaskRightsReview, require_rights

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x') as file:
        json.dump(value, file, indent=2)
        file.write('\n')


def preflight(review):
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert all(sha(path) == expected for path, expected in review['assets'].items())
    assert not Path(review['work']).exists() and not (HERE / 'started.json').exists()
    for row in review['tasks']:
        pack = BenchmarkPack.model_validate(load(row['pack']))
        task = pack.task(row['task_id'])
        decision = TaskRightsReview.model_validate(load(row['decision']))
        assert decision.local_execution_allowed and decision.provider_disclosure_allowed
        assert content_digest(decision) == row['decision_sha256']
        assert decision.assets == {asset.path: asset.sha256 for asset in task.assets}
        assert row['public_files'] == {asset.path: asset.sha256 for asset in task.assets
                                       if asset.role in ('instruction', 'input')}
        assert task_input(pack, Path(row['pack_root']), task.task_id)['task_archive_sha256'] == row['public_archive_sha256']


def apply(review, digest):
    preflight(review)
    assert load(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': digest}
    work = Path(review['work'])
    work.mkdir(mode=0o700)
    write(HERE / 'started.json', {'review_sha256': digest, 'models': 0})
    records = {}
    database = work / 'definitions.sqlite3'
    manifest = work / 'aeep.json'
    write(manifest, {'version': '0.2', 'database': str(database), 'executors': []})
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'src'), 'HOME': str(work), 'LC_ALL': 'C'}

    def cli(*argv):
        reply = subprocess.run([sys.executable, '-B', '-m', *argv], env=env, cwd=ROOT,
                               capture_output=True, text=True, timeout=20)
        assert reply.returncode == 0
        return json.loads(reply.stdout)

    for row in review['tasks']:
        identity = row['decision_sha256']
        assert cli('aeep_toolkit', 'workflow', 'define-rights', '--file', row['decision'],
                   '--manifest', str(manifest)) == {
                       'rights_review_ref': identity, 'reviewed': False, 'execution_authorized': False,
                   }
        assert cli('aeep', 'assess', '--manifest', str(manifest), 'review', identity) == {
            'digest': identity, 'reviewed': True,
        }
        pack = BenchmarkPack.model_validate(load(row['pack']))
        task = pack.task(row['task_id']).model_copy(update={'rights_review_ref': identity})
        bound = pack.model_copy(update={'tasks': (task,)})
        with ReceiptStore(database) as store:
            require_rights(AssessmentRepository(store), bound, (task.task_id,))
        file = work / (task.task_id + '-bound-pack.json')
        write(file, bound.model_dump(mode='json'))
        records[task.task_id] = {'review_ref': identity, 'bound_pack_sha256': sha(file)}
    write(HERE / 'result.json', {'review_sha256': digest, 'records': records, 'dispatch_authorized': False, 'models': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--preflight')
    flags.add_argument('--apply-approved')
    args = parser.parse_args()
    path = HERE / 'operation-review.json'
    digest = sha(path)
    assert digest == (args.preflight or args.apply_approved)
    if args.preflight:
        preflight(load(path))
        print(json.dumps({'review_sha256': digest, 'preflight_passed': True, 'models': 0}))
    else:
        apply(load(path), digest)
