"""Read-only successor audit, preserving the first audit and all runtime helpers."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = OUT / 'audit-resources.py'
BASE_SHA256 = '8516bb3ff7c2c2c7ce2707793d6553cea5f8dda8dee9f92847df5733c9414703'


def audit(inspect_docker=False):
    if BASE.is_symlink() or hashlib.sha256(BASE.read_bytes()).hexdigest() != BASE_SHA256:
        raise ValueError('original read-only audit helper changed')
    spec = importlib.util.spec_from_file_location('diagnostic_resource_audit_v1', BASE)
    if spec is None or spec.loader is None:
        raise ValueError('audit helper loader unavailable')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    result = previous.audit(inspect_docker)
    amendment_path = OUT / 'finite-diagnostic-amendment-v2.json'
    amendment = previous.document(amendment_path)
    limits = {key: amendment[key] for key in ('total_maximum_operations', 'total_maximum_model_turns',
                                             'total_maximum_reserved_seconds', 'cash_ceiling_usd')}
    if limits != {'total_maximum_operations': 18, 'total_maximum_model_turns': 2,
                  'total_maximum_reserved_seconds': 1596, 'cash_ceiling_usd': 0}:
        raise ValueError('successor diagnostic amendment limits changed')
    phases = result['phases']
    reservations = [phase['reserved'] for phase in phases if 'reserved' in phase]
    reserved = {key: sum(item[key] for item in reservations)
                for key in ('max_operations', 'max_model_turns', 'max_elapsed_seconds')}
    terminal = {}
    for name in ('diagnostic-result.json', 'diagnostic-v2-result.json'):
        path = OUT / name
        entry = {'present': path.is_file()}
        if entry['present']:
            value = previous.document(path)
            entry.update({key: value[key] for key in ('result_status', 'stage', 'failure_stage', 'error_type',
                'host_receipt_status', 'host_execution_success', 'operation_settled', 'cleanup_confirmed',
                'source_unchanged', 'model_turn_count_observed', 'elapsed_seconds') if key in value})
            entry['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        terminal[name] = entry
    result.update(schema_version='assessment.diagnostic-resource-audit.v2',
                  audit_base_sha256=BASE_SHA256,
                  finite_amendment_sha256=hashlib.sha256(amendment_path.read_bytes()).hexdigest(),
                  aggregate_limits=limits, aggregate_reserved=reserved,
                  reservations_within_limits=(reserved['max_operations'] <= 18
                      and reserved['max_model_turns'] <= 2 and reserved['max_elapsed_seconds'] <= 1596),
                  expected_operation_count_present=len(reservations) == 18,
                  all_observed_operations_settled=bool(phases) and all(p['state'] == 'complete' for p in phases),
                  diagnostic_results=terminal,
                  terminal_diagnostic_present=terminal['diagnostic-v2-result.json']['present'],
                  both_diagnostic_results_present=all(item['present'] for item in terminal.values()))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-docker', action='store_true')
    args = parser.parse_args()
    print(json.dumps(audit(args.inspect_docker), indent=2, sort_keys=True))
