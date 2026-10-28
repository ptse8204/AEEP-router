"""Read cached corpus metadata only; never fetch, execute, grade or adopt a case."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    manifest=ROOT/'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json'
    data=json.loads(manifest.read_text());rows={}
    for source in data['sources']:
        path=ROOT/source['private_cache'];assert sha(path)==source['sha256']
        for record in json.loads(path.read_text())['rows']:
            row=record['row'];rows[row['instance_id']]=row
    pool_path=HERE.parent/'repository-pymdown-portable-20261028/provisional-pool.json'
    pool=json.loads(pool_path.read_text());current=json.loads((ROOT/pool['cases_file']).read_text())
    origins={(c['source_repository'].removeprefix('https://github.com/').casefold(),c['source_revision']) for c in current}
    inventory=ROOT/'reports/toolkit-v2/c13/repository-suite-integration-20261022/cohort-inventory.json'
    review=[]
    for item in json.loads(inventory.read_text())['rows']:
        if (item['repo'].casefold(),item['base_commit']) in origins:continue
        row=rows[item['instance_id']];names=row['FAIL_TO_PASS']+row['PASS_TO_PASS']
        spaces=[n for n in names if any(c.isspace() for c in n)]
        incomplete=[n for n in names if '[' in n.rsplit('::',1)[-1] and not n.endswith(']')]
        if not spaces and not incomplete:continue
        roots=set();root_blocker=False
        for name in names:
            parts=name.split('::')[0].split('/')
            index=next((i for i,p in enumerate(parts[:-1]) if p in ('test','tests','testing')),None)
            if index is None:root_blocker=True
            else:roots.add('/'.join(parts[:index+1]))
        review.append({'id':item['instance_id'],'repository':item['repo'],'revision':item['base_commit'],
            'family_hint_only':item['family_hint'],'required_identities':len(names),'whitespace_identities':len(spaces),
            'incomplete_parameter_aliases':len(incomplete),'test_roots':sorted(roots),'missing_recognized_test_root':root_blocker,
            'metadata_blockers':item['metadata_blockers'],'declared_python':item['declared_python'],
            'next_requirement':'Source-literal one-to-one mapping and pre-body native collection; never infer a full name from a truncated alias.' if incomplete else 'Freeze full metadata identities and confirm them by native collection before body grading.',
            'runtime_reference_and_semantic_faults':'UNVERIFIED','adopted':False})
    review.sort(key=lambda r:(bool(r['metadata_blockers']),r['missing_recognized_test_root'],hashlib.sha256(('aeep-native-readiness-v1:'+r['id']).encode()).hexdigest()))
    result={'metadata_only':True,'metadata_manifest_sha256':sha(manifest),'inventory_sha256':sha(inventory),'current_pool_sha256':sha(pool_path),
        'current_cases':62,'required_cases':141,'family_gaps':{'single-file-repair':22,'multi-file-repair':25,'contract-audit':32},
        'identity_affected_unpooled_rows':len(review),'repository_groups':len({r['repository'] for r in review}),
        'family_hints':dict(Counter(r['family_hint_only'] for r in review)),'candidates':review,
        'priority':'Validate the reusable native observer first;then review independent cached candidates as a batch. Metadata counts are not workload readiness or proof that these cases fill the79-case gap.',
        'unknowns':['Current source/image runtime closure,source licensing,semantic file scope,source-literal identity mapping,reference/counterexample reproduction,independence and stage applicability remain case-specific.','Rows may have earlier exclusions;preserve those outcomes and resolve their exact causes before proposing execution.','Family hints need source-body review. Native identities cannot repair missing dependencies or weak issue assertions.'],
        'downloads_installs_containers_models_or_grant_debits':0,'cases_adopted':0,'scientific_thresholds_changed':False}
    with(HERE/'metadata-readiness.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('candidates','unknowns')}))

if __name__=='__main__':main()
