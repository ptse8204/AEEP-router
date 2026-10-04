"""Execute the unchanged generator with an exact storage-only reviewed amendment."""
import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
HELPER=OUT/'c-workbook-qualification-materialize-20261003.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
async def main():
 review=OUT/'c-workbook-materialization-storage-amendment-review.json'
 if sha(review)!=sys.argv[1]:raise ValueError('exact amendment review required')
 v=json.loads(review.read_text())
 if not v['execution_authorized'] or v['wrapper_sha256']!=sha(Path(__file__)) or v['helper_sha256']!=sha(HELPER):raise ValueError('reviewed helpers changed')
 for name,digest in v['input_files'].items():
  if sha(OUT/name)!=digest:raise ValueError('amendment input changed')
 spec=importlib.util.spec_from_file_location('c_materializer_frozen',HELPER);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.REQUEST_REVIEW=OUT/'c-workbook-qualification-materialization-request-review-v2.json'
 m.APPROVAL_MARKER=OUT/'c-workbook-qualification-materialization-approved-v2.json'
 await m.execute(sha(m.REQUEST_REVIEW))
if __name__=='__main__':asyncio.run(main())
