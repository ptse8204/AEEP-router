"""Consolidate audited reproduction evidence while retaining each runtime binding."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'.aeep/repository-provisional-pool-after-batch-20261022'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    entries={};inputs=[]
    manifests=[HERE.parent/'repository-compact-patches-20261022/provisional-pool.json',HERE/'recovered-single-file-cases.json']
    for manifest in manifests:
        meta=json.loads(manifest.read_text());path=ROOT/meta['cases_file'];assert sha(path)==meta['cases_file_sha256']
        inputs.append({'manifest':str(manifest.relative_to(ROOT)),'manifest_sha256':sha(manifest),'cases_file':str(path.relative_to(ROOT)),'cases_sha256':sha(path)})
        for case in json.loads(path.read_text()):
            identity=case['input']['task_id'];assert identity not in entries
            entries[identity]={'case':case,'evidence_manifest':str(manifest.relative_to(ROOT)),'source_runtime_binding':'Preserve the referenced manifest; old runtime conformance is not transferred.'}
    audit=json.loads((HERE/'runtime-execution/completion-audit.json').read_text());result=json.loads((HERE/'execution-result.json').read_text());build=json.loads((HERE/'build-result.json').read_text());prepared=json.loads((HERE/'prepared-cases.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent'] and result['receipt_integrity_passed']
    assert audit['canonical_receipts_reopened']==84 and len(audit['eligible_cases'])==15
    assert result['canonical_operations']==87 and result['source_unchanged'] and build['passed']
    before,after=build['grant_before'],audit['grant_after'];assert after[0]-before[0]==87 and after[1]==before[1] and after[3]==before[3]
    path=ROOT/prepared['cases_file'];assert sha(path)==prepared['cases_file_sha256'];inputs.append({'manifest':str((HERE/'runtime-execution/completion-audit.json').relative_to(ROOT)),'manifest_sha256':sha(HERE/'runtime-execution/completion-audit.json'),'cases_file':str(path.relative_to(ROOT)),'cases_sha256':sha(path)})
    for case in json.loads(path.read_text()):
        identity=case['input']['task_id']
        if identity not in audit['eligible_cases']:continue
        assert identity not in entries
        entries[identity]={'case':case,'evidence_manifest':str((HERE/'runtime-execution/completion-audit.json').relative_to(ROOT)),'source_digest':json.loads((HERE/'runtime-execution/execution-result.json').read_text())['source_digest'],'image_id':build['image_id'],'image_tag':build['target_tag']}
    assert len(entries)==35 and len({(v['case']['source_repository'].casefold(),v['case']['source_revision']) for v in entries.values()})==35
    assert len({v['case']['input']['source_sha256'] for v in entries.values()})==35
    OUT.mkdir(exist_ok=False);path=OUT/'cases.json';path.write_text(json.dumps([v['case'] for v in entries.values()],indent=2)+'\n')
    counts=dict(Counter(v['case']['input']['family'] for v in entries.values()))
    result={'cases_file':str(path.relative_to(ROOT)),'cases_file_sha256':sha(path),'inputs':inputs,'case_count':35,'repository_count':len({v['case']['source_repository'].casefold() for v in entries.values()}),'family_counts':counts,
        'required_reference_identities':sum(len(v['case']['truth']['fail_to_pass'])+len(v['case']['truth']['pass_to_pass']) for v in entries.values()),
        'source_runtime_bindings':{key:{k:x for k,x in v.items() if k!='case'} for key,v in entries.items()},
        'target_family_totals':{k:47 for k in counts},'missing_family_counts':{k:47-v for k,v in counts.items()},
        'cases_adopted':0,'stages_frozen':False,'qualification':False,'comparative_usefulness':False,'selection':False,'historical_results_unchanged':True,'new_external_calls_for_consolidation':0,
        'latest_grant':after,'batch_canonical_operations_including_build':87,'batch_charged_elapsed_seconds_including_build':after[2]-before[2],
        'new_image':{'tag':build['target_tag'],'id':build['image_id'],'growth_bytes':build['image_growth_bytes'],'retained':True},'old_image_retained':True}
    assert counts=={'single-file-repair':12,'contract-audit':5,'multi-file-repair':18}
    (HERE/'provisional-pool.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('case_count','repository_count','family_counts','required_reference_identities','missing_family_counts','batch_charged_elapsed_seconds_including_build')}))


if __name__=='__main__':main()
