"""Read existing exact validation records; optional container failure is retained."""
import hashlib,json
from pathlib import Path
REQUIRED=('compileall','schema','ruff','mypy','policy','pytest','coverage-pytest','coverage-report','coverage-json','critical-coverage','assessment-coverage','node','economic','dsh','dsh-live','dsh-comparison','dsh-native-plan','job','provider','router-complete','package-build')
def validate(root,review,source):
    records=review.get('native_validation_records');assert isinstance(records,dict) and records,'Final native/software validation records not bound'
    checks={};optional=[]
    for relative,expected in records.items():
        path=Path(root)/relative
        with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==expected
        record=json.loads(path.read_text());assert record['source_digest']==source
        for check in record['checks']:
            name=check['name']
            if name=='container-all':optional.append({'exit_code':check['exit_code'],'source_unchanged':check.get('source_unchanged')});continue
            assert name not in checks,'Duplicate phase evidence';checks[name]=check
    assert set(REQUIRED)==set(checks),'Required native/software phase missing or unexpected'
    assert all(checks[name]['exit_code']==0 and checks[name].get('source_unchanged') is True for name in REQUIRED),'Applicable native/software phase failed or drifted'
    assert optional,'Historical optional container outcome must remain retained'
    return {'required_native_software_phases':list(REQUIRED),'optional_container_outcomes':optional,'container_conformance_established':False,'classification':'Native container-free execution prerequisite only; no container or whole-release pass inferred'}
