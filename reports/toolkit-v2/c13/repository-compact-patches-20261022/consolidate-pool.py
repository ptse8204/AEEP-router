"""Index retained reproduction records without rerunning external software."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.aeep/repository-provisional-pool-20261022'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert not OUT.exists()
    entries = {}
    inputs = []
    prior = [
        (HERE.parent / 'repository-declared-tests-20261022/composed-screening-reproduction.json', 'f694024c'),
        (HERE.parent / 'repository-corpus-expansion-20261022/reproduced-candidate-pool.json', 'f694024c'),
    ]
    for manifest, source in prior:
        metadata = json.loads(manifest.read_text())
        path = ROOT / metadata['cases_file']
        assert sha(path) == metadata['cases_file_sha256']
        inputs.append({'manifest': str(manifest.relative_to(ROOT)), 'manifest_sha256': sha(manifest),
                       'cases_file': str(path.relative_to(ROOT)), 'cases_sha256': sha(path)})
        for case in json.loads(path.read_text()):
            identity = case['input']['task_id']
            assert identity not in entries
            entries[identity] = {'case': case, 'reproduction_source': source, 'evidence_manifest': str(manifest.relative_to(ROOT))}
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    path = ROOT / prepared['cases_file']
    assert sha(path) == prepared['cases_file_sha256']
    audit = json.loads((HERE / 'completion-audit.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    inputs.append({'manifest': str((HERE / 'completion-audit.json').relative_to(ROOT)), 'manifest_sha256': sha(HERE / 'completion-audit.json'),
                   'cases_file': str(path.relative_to(ROOT)), 'cases_sha256': sha(path)})
    for case in json.loads(path.read_text()):
        identity = case['input']['task_id']
        if identity in audit['eligible_cases']:
            entries[identity] = {'case': case, 'reproduction_source': json.loads((HERE / 'execution-result.json').read_text())['source_digest'],
                                 'evidence_manifest': str((HERE / 'completion-audit.json').relative_to(ROOT))}
    assert len(entries) == 18
    assert len({(v['case']['source_repository'].casefold(), v['case']['source_revision']) for v in entries.values()}) == 18
    assert len({v['case']['input']['source_sha256'] for v in entries.values()}) == 18
    OUT.mkdir()
    path = OUT / 'cases.json'
    path.write_text(json.dumps([v['case'] for v in entries.values()], indent=2) + '\n')
    manifest = {'cases_file': str(path.relative_to(ROOT)), 'cases_file_sha256': sha(path), 'inputs': inputs,
        'case_count': len(entries), 'repository_count': len({v['case']['source_repository'].casefold() for v in entries.values()}),
        'family_counts': dict(Counter(v['case']['input']['family'] for v in entries.values())),
        'required_reference_identities': sum(len(v['case']['truth']['fail_to_pass']) + len(v['case']['truth']['pass_to_pass']) for v in entries.values()),
        'source_bindings': {identity: {k: v[k] for k in ('reproduction_source', 'evidence_manifest')} for identity, v in entries.items()},
        'duplicate_sqlglot_5256': 'Use the newly reproduced v3 record; retain both historical observations. Count this task once.',
        'cases_adopted': 0, 'stage_assignments_frozen': False, 'external_code_executed': False,
        'current_source_conformance_transferred_to_old_records': False, 'qualification': False, 'comparative_usefulness': False, 'selection': False}
    (HERE / 'provisional-pool.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('case_count', 'repository_count', 'family_counts', 'required_reference_identities')}))


if __name__ == '__main__':
    main()
