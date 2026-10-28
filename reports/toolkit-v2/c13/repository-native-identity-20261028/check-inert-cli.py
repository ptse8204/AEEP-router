"""Exercise the actual cases through the inert source CLI; no candidate execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def main():
    meta=json.loads((HERE/'execution-cases.json').read_text());cases=json.loads((ROOT/meta['cases_file']).read_text())
    for case in cases:case.update(split='development',used_for_development=True)
    with tempfile.TemporaryDirectory(prefix='aeep-FIRST-PARTY-inert-native-export-',dir=ROOT/'.aeep') as temp:
        path=Path(temp)/'cases.json';path.write_text(json.dumps(cases))
        assert path.stat().st_size<1024**2
        child=subprocess.run([sys.executable,'-m','aeep_toolkit','repository-suite-recipe','--cases',str(path)],cwd=ROOT,env={**os.environ,'PYTHONPATH':'src'},text=True,capture_output=True,timeout=30)
        assert child.returncode==0,child.stderr
        value=json.loads(child.stdout);assert len(value['generator_config']['cases'])==3
        native=[c for c in value['generator_config']['cases'] if c['schema_version']=='assessment.repository-suite-case.v6']
        assert len(native)==1 and len(native[0]['truth']['fail_to_pass']+native[0]['truth']['pass_to_pass'])==915
        assert native[0]['truth']['identity_format']=='pytest-native-v1'
        assert 'OPERATOR_REVIEW = False' in value['extension']['grader']['config']['argv'][-1]
        result={'passed':True,'actual_source_cli_export':True,'metadata_file_bytes':path.stat().st_size,'export_sha256':hashlib.sha256(child.stdout.encode()).hexdigest(),'native_required_identities':915,'external_source_or_wheels_executed':False,'new_models_installs_containers':0,'raw_export_retained':False}
    assert not Path(temp).exists();result['owned_scratch_removed']=True
    with(HERE/'inert-cli-check.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()
