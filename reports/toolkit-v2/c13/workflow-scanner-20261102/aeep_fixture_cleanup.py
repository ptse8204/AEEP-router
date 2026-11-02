"""Local verification fixture cleanup after monkeypatch teardown; no product hooks."""
from __future__ import annotations
import json,os,shutil
from pathlib import Path
import pytest

REMOVED=[]
KEPT=[]

@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef,request):
    outcome=yield
    if fixturedef.argname=='tmp_path' and outcome.excinfo is None:
        request.node._aeep_owned_tmp=outcome.get_result()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    results=getattr(item,'_aeep_phase_results',{})
    results[report.when]=report.outcome
    item._aeep_phase_results=results
    if report.when!='teardown':return
    path=getattr(item,'_aeep_owned_tmp',None)
    if path is None:return
    path=Path(path)
    root=item.config._tmp_path_factory.getbasetemp()
    if not all(results.get(phase)=='passed' for phase in ('setup','call','teardown')):
        KEPT.append(str(path));return
    if path.parent!=root or path.is_symlink() or path.resolve()!=path or not path.is_dir():
        KEPT.append(str(path));return
    # The original test and every fixture finalizer have completed. In particular,
    # os.open/Path hooks used by credential-denial assertions are now restored.
    assert path.stat().st_uid==os.getuid()
    shutil.rmtree(path)
    REMOVED.append(str(path))

def pytest_sessionfinish(session,exitstatus):
    record={'policy':'Remove only this run passing tmp_path fixtures after all fixture teardown; preserve failures/unknowns/older roots.',
        'removed':REMOVED,'kept':KEPT,'exit_status':int(exitstatus),'source_assertions_changed':False,'upstream_executed_by_plugin':False}
    target=os.environ.get('AEEP_FIXTURE_CLEANUP_RECORD')
    if target:
        with Path(target).open('x') as stream:json.dump(record,stream,indent=2)
