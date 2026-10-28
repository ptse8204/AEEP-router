"""Check cached metadata/source/license pins and image ancestry; no containers."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    meta=json.loads((HERE/'prepared-seeds.json').read_text());records=json.loads((ROOT/meta['records_file']).read_text())
    manifest=ROOT/'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json';catalog=json.loads(manifest.read_text());rows={}
    for record in catalog['sources']:
        p=ROOT/record['private_cache'];assert sha(p)==record['sha256']
        for value in json.loads(p.read_text())['rows']:rows[value['row']['instance_id']]=value['row']
    candidates={}
    for p in (ROOT/'reports/toolkit-v2/c13').glob('*/*source*review*.json'):
        value=json.loads(p.read_text())
        if not isinstance(value,dict) or not isinstance(value.get('sources'),list):continue
        for record in value['sources']:
            if isinstance(record,dict) and record.get('instance_id') in {x['original_issue_id'] for x in records}:
                candidates.setdefault(record['instance_id'],[]).append((p,record))
    for record in records:
        folder=ROOT/record['source_cache'];row=json.loads((folder/'row.json').read_text());expected=rows[record['original_issue_id']]
        for key in ('repo','instance_id','base_commit','patch','test_patch','FAIL_TO_PASS','PASS_TO_PASS','problem_statement','interface'):assert row[key]==expected[key]
        matching=[(p,v) for p,v in candidates[record['original_issue_id']] if v.get('private_cache')==record['source_cache'] and v.get('archive_sha256')==sha(folder/'source.tar.gz')]
        assert matching,record['original_issue_id']
        for license in record.get('license_records',[]):assert sha(ROOT/license['path'])==license['sha256']
    wheel=meta['portable_identify'];path=ROOT/wheel['private_cache'];assert sha(path)==wheel['sha256']
    with zipfile.ZipFile(path) as z:
        text=z.read('identify-2.6.15.dist-info/WHEEL').decode();assert 'Root-Is-Purelib: true' in text and 'Tag: py2-none-any' in text
        assert not any(n.endswith(('.so','.pyd','.dylib','.pth')) for n in z.namelist())
    for license in wheel['licenses']:assert sha(ROOT/license['retained'])==license['sha256']
    image='sha256:9f473c493b7af1854922807d2acbdcbe3b955313dc57f203e6f73c9c50f9ea85'
    ancestor='sha256:b0eb4add50887814206ad86dc0b685003382da55a44b166711438409769a9661'
    def layers(identity):
        raw=subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','image','inspect',identity,'--format','{{json .RootFS.Layers}}'],timeout=20)
        return json.loads(raw)
    current=layers(image);before=layers(ancestor);assert current[:len(before)]==before
    installed=json.loads((HERE.parent/'repository-independent-sources-20261024/runtime-install-review.json').read_text())['pins']
    assert {'sqlalchemy','greenlet','msgspec'}<={p['project'].lower() for p in installed}
    result={'passed':True,'three_seed_metadata_records_match_pinned_dataset':True,'three_original_archives_match_historical_reviews':True,'source_and_identify_licenses_hash_checked':True,'identify_pure_zip_closure_reviewed_without_import':True,'retained_image':image,'verified_ancestor':ancestor,'ancestor_layers':len(before),'current_layers':len(current),'actual_current_imports_and_versions':'UNVERIFIED until the approved runtime probe;ancestry/selected pins are preparation evidence only.','source_caches_only':True,'new_containers_downloads_installs_models_or_grant_debits':0}
    with(HERE/'seed-provenance-check.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()
