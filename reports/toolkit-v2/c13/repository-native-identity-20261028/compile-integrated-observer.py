"""Compile only first-party adapter text as a frozen operator program; no execution."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
runtime=HERE.parents[3]/'integrations/assessment-runtime'
source=(runtime/'repository_suite_native_capture.py').read_text();template=(runtime/'repository_suite_native_program.py').read_text()
assert template.count('OPERATOR_REVIEW = False')==1
template=template.replace('OPERATOR_REVIEW = False','OPERATOR_REVIEW = True')
assert template.count("'__AEEP_NATIVE_CAPTURE_SOURCE__'")==1
program=template.replace("'__AEEP_NATIVE_CAPTURE_SOURCE__'",repr(source));ast.parse(source);ast.parse(program)
with(HERE/'observer-v6-integrated.py').open('x') as f:f.write(program)
print(json.dumps({'compiled_only':True,'observer_sha256':hashlib.sha256(program.encode()).hexdigest(),'capture_sha256':hashlib.sha256(source.encode()).hexdigest(),'execution':False}))
