"""Check the new docs snapshot using the previously reviewed cached tool bytes."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


review_file = HERE/'operation-review.json'
review = json.loads(review_file.read_bytes())
authority = json.loads((HERE/'delegated-authority.json').read_bytes())
identity = sha(review_file)
assert sys.argv[1:] == ['--execute-delegated',identity]
assert authority['first_attempt'] and authority['review_sha256']==identity
assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'])
assert shutil.disk_usage(ROOT).free>=52*1024**3
for file,digest in review['pins'].items():
    assert sha(file)==digest,file
assert not (HERE/'result.json').exists()
source=Path(review['tool_review']).parent/'run-review.py'
spec=importlib.util.spec_from_file_location('cached_docs',source)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
tools=json.loads(Path(review['tool_review']).read_bytes())
runner.verify(tools)
assert json.loads((source.parent/'sandbox-preflight.json').read_bytes())['passed']
shutil.copyfile(source.parent/'sandbox-template.sb',HERE/'sandbox-template.sb')
runner.HERE=HERE
runtime,state=runner.setup(tools,identity)
env={'PATH':str(runtime/'bin')+':/usr/local/bin:/usr/bin:/bin',
     'HOME':str(runtime/'home'),'TMPDIR':str(runtime/'tmp'),'LC_ALL':'C'}
start=time.monotonic()
with (HERE/'docs.log').open('x') as log:
    process=subprocess.run(['/usr/bin/make','docs-check','LYCHEE='+str(runtime/'bin/lychee-sandbox')],
                           env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
intact=runner.tools_state(runtime)==state['files'] and all(sha(file)==digest for file,digest in review['pins'].items())
result={'passed':process.returncode==0 and intact,'exit_code':process.returncode,'review_sha256':identity,
        'inputs_and_tools_unchanged':intact,'elapsed_seconds':time.monotonic()-start,'runtime_retained':str(runtime),
        'document_count':len(tools['documents']),'network':False,'models':0}
with (HERE/'result.json').open('x') as f:
    json.dump(result,f,indent=2); f.write('\n')
print(json.dumps(result))
raise SystemExit(not result['passed'])
