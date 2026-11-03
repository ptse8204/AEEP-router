"""First-party native sandbox/Git probe; never import the upstream evaluator."""
from __future__ import annotations
import json,os,socket,subprocess,sys,tempfile
from pathlib import Path

def denied(call):
    try:call()
    except PermissionError:return True
    except OSError as error:return error.errno in {1,13}
    return False

def main():
    p=json.loads(sys.stdin.buffer.read(16385));work=Path.cwd()
    checks={
      'outside_read_denied':denied(lambda:Path(p['outside_canary']).read_bytes()),
      'outside_tmp_read_denied':denied(lambda:Path(p['outside_tmp_canary']).read_bytes()),
      'outside_write_denied':denied(lambda:Path(p['outside_write']).write_text('owned-boundary-probe')),
      'response_write_denied':denied(lambda:(work/'responses/untrusted-write').write_text('blocked')),
      'candidate_write_denied':denied(lambda:(work/'candidate/untrusted-write').write_text('blocked')),
    }
    def connect():
      with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as channel:channel.connect(('127.0.0.1',9))
    checks['network_denied']=denied(connect)
    scratch=Path(tempfile.mkdtemp(prefix='git-boundary-',dir=work));(scratch/'owned.txt').write_text('first-party Git fixture')
    commands=[['init','-b','main'],['config','user.email','eval@agent-skill-eval.local'],['config','user.name','Skill Eval'],['add','.'],['commit','-m','Initial commit','--allow-empty'],['branch','-a'],['status','--porcelain']]
    git_ok=True
    for arguments in commands:
      result=subprocess.run([p['git_wrapper'],*arguments],cwd=scratch,capture_output=True,timeout=5)
      if result.returncode:git_ok=False;break
    checks['git_init_commit_and_snapshot']=git_ok
    print(json.dumps({'passed':all(checks.values()),'checks':checks,'actual_upstream_imports':0,'actual_model_calls':0}))

if __name__=='__main__':main()
