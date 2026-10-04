"""Read-only bounded diagnostic audit. Prints JSON; never repairs or cleans up."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
DATABASE = ROOT / '.aeep/live-review-v3/aeep.sqlite3'


def document(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_size > 4_000_000:
        raise ValueError('unsafe or oversized audit input')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('audit input must be an object')
    return value


def records(db, kind, identity):
    row = db.execute('SELECT digest,payload_json FROM assessment_records WHERE kind=? AND (id=? OR digest=?) LIMIT 1',
                     (kind, identity, identity)).fetchone()
    return (row['digest'], json.loads(row['payload_json'])) if row else (None, None)


def references(value, match):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if match(key):
                if isinstance(item, str):
                    found.add(item)
                elif isinstance(item, list):
                    found.update(x for x in item if isinstance(x, str))
                elif isinstance(item, dict):
                    found.update(x for x in item.values() if isinstance(x, str))
            found.update(references(item, match))
    elif isinstance(value, list):
        for item in value:
            found.update(references(item, match))
    return found


def docker_json(argv):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=8, check=False)
        if result.returncode or len(result.stdout) > 65536:
            return {'available': False, 'returncode': result.returncode}
        return {'available': True, 'value': json.loads(result.stdout)}
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {'available': False, 'error_type': type(exc).__name__}


def audit(inspect_docker=False):
    baseline = document(OUT / 'preflight.json')
    profile = document(OUT / 'c-current-profile-v2.json')
    request_ids, operation_ids = set(), set()
    result_docs = {}
    for path in sorted(OUT.glob('*.json')):
        if not any(word in path.name for word in ('result', 'review', 'started', 'preparation', 'bundle', 'request')):
            continue
        data = document(path)
        if isinstance(data.get('request_id'), str):
            request_ids.add(data['request_id'])
        request_ids.update(x for x in data.get('request_ids', []) if isinstance(x, str))
        if isinstance(data.get('request'), dict):
            request_ids.add(data['request'].get('plan_id'))
        if isinstance(data.get('operation_id'), str):
            operation_ids.add(data['operation_id'])
        operation_ids.update(data.get('measured_operation_seconds', {}))
        for worker in data.get('workers', {}).values():
            if isinstance(worker, dict) and isinstance(worker.get('request_id'), str):
                request_ids.add(worker['request_id'])
        if 'result' in path.name:
            result_docs[path.name] = data
    request_ids.discard(None)
    phases, links = [], []
    preexisting = []
    with sqlite3.connect(DATABASE.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        grant = dict(db.execute('SELECT * FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone())
        for old in baseline['pending_operations']:
            row = db.execute('SELECT * FROM assessment_operations WHERE id=?', (old['id'],)).fetchone()
            now = dict(row) if row else None
            preexisting.append({'id': old['id'], 'unchanged': now == old, 'current_state': now['state'] if now else None})
        for request_id in sorted(request_ids):
            rows = db.execute("SELECT id,payload_json FROM assessment_records WHERE kind='operation_start' AND json_extract(payload_json,'$.plan_id')=?", (request_id,))
            operation_ids.update(row['id'] for row in rows)
        for operation_id in sorted(operation_ids):
            row = db.execute('SELECT * FROM assessment_operations WHERE id=?', (operation_id,)).fetchone()
            if row is None:
                phases.append({'operation_id': operation_id, 'state': 'not_reserved'})
                continue
            start_digest, start = records(db, 'operation_start', operation_id)
            measurement_digest, measured = records(db, 'operation_measurement', operation_id)
            phases.append({'operation_id': operation_id, 'grant_id': row['grant_id'], 'state': row['state'],
                           'stage': start.get('stage') if start else None,
                           'reserved': json.loads(row['reserved_json']), 'start_digest': start_digest,
                           'measurement_digest': measurement_digest,
                           'elapsed_seconds': measured.get('elapsed_seconds') if measured else None,
                           'accounting': measured.get('accounting') if measured else None,
                           'resources': measured.get('resources') if measured else None})
        for filename, data in result_docs.items():
            probe_refs = references(data, lambda key: key in {'probe_digest', 'probe_digests', 'supervisor_probe_digests'})
            for ref in sorted(probe_refs):
                digest, probe = records(db, 'boundary_probe', ref)
                if probe is None:
                    links.append({'result': filename, 'probe_digest': ref, 'available': False})
                    continue
                parent_ref = probe.get('charged_operation_digest')
                parent_digest, parent = records(db, 'operation_start', parent_ref) if parent_ref else (None, None)
                operation_id = parent.get('operation_id') if parent else None
                row = db.execute('SELECT grant_id,state FROM assessment_operations WHERE id=?', (operation_id,)).fetchone()
                measure_digest, measured = records(db, 'operation_measurement', operation_id) if operation_id else (None, None)
                _, request = records(db, 'conformance_request', parent.get('plan_id')) if parent else (None, None)
                links.append({'result': filename, 'probe_digest': digest, 'probe_name': probe['name'],
                              'parent_request_worker_matches': request.get('worker_digest') == probe.get('worker_digest') if request else None,
                              'probe_definition_in_parent_request': probe.get('implementation_digest') in request.get('definition_digests', []) if request else None,
                              'parent_operation_id': operation_id, 'parent_start_digest_matches': parent_digest == parent_ref and parent_ref is not None,
                              'parent_in_diagnostic': operation_id in operation_ids,
                              'parent_state': row['state'] if row else None,
                              'parent_grant_id': row['grant_id'] if row else None,
                              'measurement_present': measure_digest is not None,
                              'measurement_seconds': measured.get('elapsed_seconds') if measured else None})
    workers = {}
    image_refs = set()
    for role in ('control', 'treatment'):
        worker = profile['component']['composed'][role]['config']['managed_worker']
        workers[role] = {'worker_id': worker['worker_id'], 'image': worker['image']}
        image_refs.add(worker['image'])
    known_containers = {}
    summaries = {}
    for filename, data in result_docs.items():
        selected = {key: data[key] for key in ('status', 'result_status', 'model_turns', 'model_turn_count_observed',
                    'elapsed_seconds', 'cleanup_confirmed', 'proxy_restored_stopped', 'source_unchanged',
                    'operation_settled', 'host_resources', 'host_accounting', 'receipt_resources') if key in data}
        selected['workers'] = {role: {key: item[key] for key in ('request_id', 'worker_digest', 'cleanup_confirmed') if key in item}
                               for role, item in data.get('workers', {}).items() if isinstance(item, dict)}
        selected['sha256'] = hashlib.sha256((OUT / filename).read_bytes()).hexdigest()
        summaries[filename] = selected
        for identity in references(data, lambda key: key in {'container_name', 'container_id', 'proxy_id'}):
            if re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', identity):
                known_containers[identity] = {'reported_by': filename}
        proxy = data.get('proxy_identity', {})
        if isinstance(proxy, dict) and isinstance(proxy.get('image'), str):
            image_refs.add(proxy['image'])
    images = {ref: {'configured_reference': ref, 'inspection': 'not_requested'} for ref in sorted(image_refs)}
    if inspect_docker:
        argv = [worker['runtime'], '--host', 'unix://' + worker['socket']]
        for ref in images:
            images[ref]['inspection'] = docker_json([*argv, 'image', 'inspect', '--format',
                '{"id":{{json .Id}},"tags":{{json .RepoTags}},"digests":{{json .RepoDigests}}}', ref])
        for identity in known_containers:
            known_containers[identity]['inspection'] = docker_json([*argv, 'container', 'inspect', '--format',
                '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"running":{{json .State.Running}},"status":{{json .State.Status}}}', identity])
    return {'schema_version': 'assessment.diagnostic-resource-audit.v1', 'observed_at': datetime.now(timezone.utc).isoformat(),
            'canonical_database_read_only': True, 'runtime_mutations': False,
            'grant': grant, 'grant_delta_since_preflight': {key: grant[key] - baseline['grant'][key]
                for key in ('operations', 'model_turns', 'elapsed_seconds')},
            'grant_delta_scope': 'all grant activity since preflight; not necessarily diagnostic-only',
            'preexisting_reserved_operations': preexisting, 'phases': phases,
            'sum_completed_operation_seconds': sum(p['elapsed_seconds'] for p in phases
                if p.get('state') == 'complete' and p.get('elapsed_seconds') is not None),
            'operation_time_scope': 'ledger operations once each; child receipts and snapshots are not added',
            'probe_parent_links': links, 'results': summaries, 'workers': workers, 'images': images,
            'known_containers': known_containers,
            'unknowns': ['Whole-system preparation/audit overhead and complete resource totals are unavailable.',
                         'Missing disposable worker identifiers remain unknown; cleanup flags retain their recorded evidence scope.',
                         'Failed Docker inspection is unavailable, not proof of removal.'],
            'terminal_diagnostic_present': any(name == 'diagnostic-result.json' for name in result_docs)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-docker', action='store_true', help='Read only exact image/container identity and state fields')
    args = parser.parse_args()
    print(json.dumps(audit(args.inspect_docker), indent=2, sort_keys=True))
