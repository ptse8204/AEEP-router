"""Prioritize cached multi-file metadata;no archive fetch,adoption or subject execution."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
NAMED={'facelessuser/pymdown-extensions','omni-us/jsonargparse','tefra/xsdata',
       'wireservice/csvkit','copier-org/copier','scientific-python/docstub',
       'pyinfra-dev/pyinfra','canopen-python/canopen','duo-labs/py_webauthn',
       'fsspec/universal_pathlib','MindscapeHQ/raygun4py','python-wheel-build/fromager',
       'marcosschroh/dataclasses-avroschema','yukinarit/pyserde'}

def main():
    metadata_path=ROOT/'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json';metadata=json.loads(metadata_path.read_text());rows={}
    for item in metadata['sources']:
        path=ROOT/item['private_cache'];assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        for item in json.loads(path.read_text())['rows']:rows[item['row']['instance_id']]=item['row']
    previous=set()
    for path in (ROOT/'reports/toolkit-v2/c13').glob('*/source-queue.json'):
        value=json.loads(path.read_text())
        previous.update(value.get('identities',[]))
        records=value.get('rows',[])
        if isinstance(records,list):previous.update(v['instance_id'] for v in records if isinstance(v,dict) and 'instance_id' in v)
    pool=json.loads((ROOT/'reports/toolkit-v2/c13/repository-effective-runtime-20261027/provisional-pool.json').read_text())
    existing=json.loads((ROOT/pool['cases_file']).read_text())
    pending=json.loads((ROOT/'.aeep/repository-large-selected-cases-20261027/cases.json').read_text())
    origins={(c['source_repository'].removeprefix('https://github.com/').casefold(),c['source_revision']) for c in [*existing,*pending]}
    inventory=json.loads((ROOT/'reports/toolkit-v2/c13/repository-suite-integration-20261022/cohort-inventory.json').read_text());selected=[];excluded=[]
    for item in inventory['rows']:
        if item['repo'] not in NAMED or item['family_hint']!='multi-file-repair' or item['metadata_blockers'] or (item['repo'].casefold(),item['base_commit']) in origins:continue
        row=rows[item['instance_id']];reasons=[];roots=set()
        for node in row['FAIL_TO_PASS']+row['PASS_TO_PASS']:
            parts=node.split('::')[0].split('/');index=next((i for i,p in enumerate(parts[:-1]) if p in ('test','tests','testing')),None)
            if index is None:reasons.append('unsupported_test_root')
            else:roots.add('/'.join(parts[:index+1]))
            terminal=node.rsplit('::',1)[-1]
            if any(c.isspace() for c in node) or ('[' in terminal and not terminal.endswith(']')):reasons.append('incomplete_or_whitespace_identity')
        if len(roots)!=1:reasons.append('non_single_protected_root')
        if reasons:excluded.append({'id':item['instance_id'],'reasons':sorted(set(reasons))});continue
        selected.append({'id':item['instance_id'],'repository':item['repo'],'revision':item['base_commit'],'family_hint':item['family_hint'],'published_source_file_count':item['published_source_file_count'],'declared_python':item['declared_python'],'required_identity_count':len(row['FAIL_TO_PASS'])+len(row['PASS_TO_PASS']),'test_root':next(iter(roots)),'provisional_only':True,'needs_semantic_multifile_review':True,'previous_queue_recorded':item['instance_id'] in previous,'needs_prior_exclusion_review':item['instance_id'] in previous})
    selected.sort(key=lambda x:hashlib.sha256(('aeep-c13-multifile-next-v1:'+x['id']).encode()).hexdigest())
    counts=Counter();bounded=[]
    for item in selected:
        if counts[item['repository']]>=2:continue
        counts[item['repository']]+=1;bounded.append(item)
    assert len(bounded)<=28
    result={'metadata_only':True,'dataset_revision':metadata['revision_before_and_after'],'metadata_manifest_sha256':hashlib.sha256(metadata_path.read_bytes()).hexdigest(),'selection_before_new_source_or_model_outcomes':True,'reason':'The51-case historical pool lacks28 multi-file tasks. Predeclare ordinary parser,markup,CLI,filesystem and schema-library candidates;avoid concentrating on a single repository or known external-service stack. Runtime feasibility remains unknown.','named_repositories':sorted(NAMED),'previous_queue_ids_recorded':len(previous),'revisit_policy':'Do not discard prior failures. Existing pool and pending6 origins excluded. Earlier queue-only rows may be reconsidered under the newly explicit larger cap,only after their prior exclusion reason and runtime/test semantics are reviewed. No automatic retry authority.','maximum_per_repository':2,'seeded_order_salt':'aeep-c13-multifile-next-v1','candidates':bounded,'metadata_exclusions':excluded,'new_archives_fetched':0,'external_code_or_models_executed':0,'cases_adopted':0,'stage_freeze':False,'scientific_thresholds_changed':False}
    (HERE/'next-multifile-metadata-queue.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'candidates':len(bounded),'repositories':len(counts),'metadata_exclusions':len(excluded),'new_reads_downloads_installs_or_models':0}))

if __name__=='__main__':main()
