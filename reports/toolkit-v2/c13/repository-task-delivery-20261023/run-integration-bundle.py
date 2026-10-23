"""Execute one approved model/package/docs bundle; preserve independent outcomes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


def main():
    assert len(sys.argv)==2 and sha(HERE/'approval-bundle.json')==sys.argv[1]
    bundle=json.loads((HERE/'approval-bundle.json').read_text());approval=json.loads((HERE/'bundle-operator-approval.json').read_text());assert approval['approved'] and approval['review_sha256']==sys.argv[1]
    assert verification_source_digest(ROOT)==bundle['source_digest'] and shutil.disk_usage(ROOT).free>=51*1024**3
    for path,expected in bundle['assets'].items():assert sha(Path(path))==expected
    assert not (HERE/'bundle-execution-started.json').exists()
    save(HERE/'bundle-execution-started.json',{'review_sha256':sys.argv[1],'automatic_retry':False})
    results=[];began=time.perf_counter()
    try:
        for name in ['model','package','docs']:
            component=bundle['components'][name];directory=Path(component['directory']);review=directory/'operation-review.json'
            assert sha(review)==component['review_sha256']
            save(directory/'operator-approval.json',{**approval,'review_sha256':component['review_sha256'],'parent_review_sha256':sys.argv[1],'authority':'Actual parent response explicitly approves this exact component. Mechanical derivation,not a separate human answer.'})
            args=component['argv']
            if name=='package':args=[*args,'--execute-reviewed-digest',digest(json.loads(review.read_text()))]
            else:args=[*args,component['review_sha256']]
            with (HERE/(name+'-component.log')).open('x') as output:
                process=subprocess.run([sys.executable,*args],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,timeout=component['maximum_driver_seconds'])
            output_path=directory/component['result_file'];observed=json.loads(output_path.read_text()) if output_path.exists() else None
            results.append({'component':name,'returncode':process.returncode,'result_file':str(output_path),'result_sha256':sha(output_path) if output_path.exists() else None,'passed':process.returncode==0 and observed is not None and observed.get(component['passed_field']) is True})
            if name=='model':
                # Independent package/docs work continues only after known container cleanup.
                docker=['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock']
                for image in bundle['model_worker_images']:
                    assert not subprocess.check_output([*docker,'ps','-a','--filter','ancestor='+image,'--format','{{.Names}}'],text=True,timeout=20).strip(),'Worker lifecycle uncertain;stop all external dispatch'
                assert subprocess.check_output([*docker,'inspect','--format','{{.State.Running}}','aeep-reviewed-model-proxy'],text=True,timeout=20).strip()=='false'
    finally:
        save(HERE/'bundle-execution-result.json',{'review_sha256':sys.argv[1],'components':results,'all_components_passed':len(results)==3 and all(item['passed'] for item in results),'source_unchanged':verification_source_digest(ROOT)==bundle['source_digest'],'driver_wall_seconds':time.perf_counter()-began,'automatic_retry':False,'formal_qualification_or_usefulness_or_selection':False})


if __name__=='__main__':main()
