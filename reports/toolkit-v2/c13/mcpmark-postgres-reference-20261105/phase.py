"""Run one pinned upstream seed or verifier with the private PostgreSQL fixture."""
import contextlib
import hashlib
import io
import json
import os
import runpy
import sys

phase = sys.argv[1]
assert phase in ('seed', 'grade')
sys.path.insert(0, '/aeep/verifier-libs')
os.environ.update(POSTGRES_HOST='127.0.0.1', POSTGRES_PORT='5432',
                  POSTGRES_USERNAME='postgres', POSTGRES_DATABASE='postgres', POSTGRES_PASSWORD='')
captured = io.StringIO()
code = 0
with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
    try:
        runpy.run_path('/aeep/upstream.py', run_name='__main__')
    except SystemExit as error:
        code = int(error.code or 0)
out = captured.getvalue()
print(json.dumps({'phase':phase,'upstream_exit_code':code,
    'output_sha256':hashlib.sha256(out.encode()).hexdigest(),
    'missing_results': 'FAIL: security_audit_results table not found' in out,
    'all_checks_passed':'All checks passed' in out,
    'runtime_error':'Error during verification:' in out or 'Error setting up environment:' in out}))
