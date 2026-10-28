"""Compile only first-party adapter text as a frozen operator program; no execution."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=(HERE/'native_capture.py').read_text();template=(HERE/'observer_template.py').read_text()
assert template.count("'__AEEP_NATIVE_CAPTURE_SOURCE__'")==1
program=template.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'",repr(source));ast.parse(source);ast.parse(program)
with(HERE/'observer-v6.py').open('x') as f:f.write(program)
print(json.dumps({'compiled_only':True,'observer_sha256':hashlib.sha256(program.encode()).hexdigest(),'capture_sha256':hashlib.sha256(source.encode()).hexdigest(),'execution':False}))
