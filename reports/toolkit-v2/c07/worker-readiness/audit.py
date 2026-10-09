"""Read only reviewed worker metadata; never inspect credentials or holdout inputs."""
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
DATABASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3')
PLAN = 'plan_d634949396264514b929eda14e505743'
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def main():
    connection = sqlite3.connect(f'file:{DATABASE}?mode=ro', uri=True)
    def record(kind, identity):
        row = connection.execute('SELECT payload_json FROM assessment_records WHERE kind=? AND (id=? OR digest=?)', (kind, identity, identity)).fetchone()
        if row is None:
            raise ValueError('missing canonical definition')
        return json.loads(row[0])

    plan = record('plan', PLAN)
    mapping = record('mapping', plan['mapping_digest'])
    source = verification_source_digest(ROOT)
    boundaries = [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM assessment_records WHERE kind='boundary_conformance'")]
    roles = {}
    for role in ('baseline', 'candidate'):
        config = mapping[role]['config']
        worker = config['managed_worker']
        raw = subprocess.check_output(DOCKER + ['image', 'inspect', worker['image'], '--format', '{{.Id}} {{.Os}}/{{.Architecture}} {{.Size}}'], text=True).strip().split()
        assert raw[0] == worker['image'] and raw[1] == worker['platform']
        roles[role] = {
            'image': raw[0], 'platform': raw[1], 'local_image_size_bytes': int(raw[2]),
            'binary': worker['binary'], 'binary_sha256': worker['binary_sha256'],
            'configuration_digest': worker['configuration_digest'],
            'dependencies_digest': worker['dependencies_digest'],
            'current_source_conformance_records': sum(b['source_digest'] == source and b['image_digest'] == raw[0] for b in boundaries),
            'model_ids': config['model_constraints']['allowed_model_ids'], 'efforts': config['reasoning_efforts'],
            'task_instructions_sha256': hashlib.sha256(config['instructions'].encode()).hexdigest(),
            'invocation': config.get('invocation'),
        }
    assert roles['baseline']['task_instructions_sha256'] == roles['candidate']['task_instructions_sha256']
    worker = mapping['candidate']['config']['managed_worker']
    network = subprocess.check_output(DOCKER + ['network', 'inspect', worker['network_id'], '--format', '{{json .Containers}}'], text=True)
    proxy = subprocess.check_output(DOCKER + ['container', 'inspect', 'aeep-reviewed-model-proxy', '--format', '{{.Id}} {{.Image}} {{.State.Status}}'], text=True).strip().split()
    result = {
        'observed_at': datetime.now(timezone.utc).isoformat(), 'source_digest': source,
        'canonical_database': str(DATABASE), 'access': 'SQLite mode=ro; selected definition metadata only',
        'historical_plan_reference': PLAN, 'historical_mapping_digest': plan['mapping_digest'],
        'subject_digest': plan['subject_digest'], 'roles': roles,
        'network_id': worker['network_id'], 'attached_containers': len(json.loads(network)),
        'proxy': {'id': proxy[0], 'image': proxy[1], 'status': proxy[2]},
        'live_ready': False,
        'remaining_engineering': [
            'Finish the C06 exact package installation/removal gate.',
            'Prepare fresh source-bound study definitions and conformance requests using the existing canonical grant and delegated scope-review path.',
            'Review and account for restarting the existing model proxy, then verify current worker boundary and model identity before trials.',
            'Freeze easy, complex and adjacent task families, independent graders, holdouts and optional exposure for value trials; never reuse historical qualification as current-source proof.',
        ],
        'not_established_as_blockers': ['new architecture decision', 'absent local images', 'exhausted assessment budget', 'missing credentials'],
        'limitations': ['Historical qualification uses required skill exposure; it is a reusable definition reference, not the V2 optional-access study.', 'No credential content or login status was accessed. A stopped proxy does not prove that sign-in is needed.', 'No historical result or counter was changed. No provider or candidate call was made.'],
        'effects': {'model_calls': 0, 'credential_reads': 0, 'containers_started': 0, 'ledger_mutations': 0},
    }
    connection.close()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
