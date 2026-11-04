"""First-party substitutions verify denial classification without any container."""
import errno, hashlib, importlib.util, json, os, socket, subprocess
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('boundary_fixture',HERE/'boundary-program.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class File:
    def __init__(self,path):self.path=str(path)
    def read_bytes(self):return b'first-party fixture'
    def read_text(self):return 'owned check'
    def exists(self):return False
    def write_text(self,value):
        if self.path.startswith('/etc/') and failure is not None:raise OSError(failure,'fixture')
request={'host_canary':'/fixture/canary','docker_socket':'/fixture/socket','binary_sha256':hashlib.sha256(b'first-party fixture').hexdigest()}
observed=[]
for failure,expected in [(errno.EPERM,True),(errno.EACCES,True),(errno.EROFS,True),(errno.EIO,False),(None,False)]:
    with patch.object(module,'Path',File),patch.dict(os.environ,{},clear=True),patch.object(socket,'create_connection',side_effect=OSError(errno.ENETUNREACH,'fixture')),patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'skillrank 0.1.5',b'')):
        result=module.check(request)
    assert result['passed'] is expected
    observed.append({'root_write_errno':failure,'expected_passed':expected})
result={'passed':True,'evidence_kind':'first_party_substitutes_only','cases':observed,'container_or_upstream_execution':False,
        'original_real_failure_cause':'UNKNOWN: original driver did not retain inner status/error fields'}
(HERE/'boundary-controls.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
