#!/Library/Frameworks/Python.framework/Versions/3.13/bin/python3
"""Proposed ASE Git boundary; only reviewed local initialization and snapshots."""
from __future__ import annotations
import hashlib,os,sys
from pathlib import Path

GIT=Path('/Applications/Xcode.app/Contents/Developer/usr/bin/git')
GIT_SHA256='775851091335fd0f0e3eba68e92667b95115208e57ad5ca312936d10edb9ffd3'
EXEC_PATH='/Applications/Xcode.app/Contents/Developer/usr/libexec/git-core'
WORKSPACE=Path('/Users/edwintse/Documents/aeep-toolkit-v2/.aeep/ase-engineering-work-20261103/scheduler')
ALLOWED=frozenset({
 ('init','-b','main'),('config','user.email','eval@agent-skill-eval.local'),
 ('config','user.name','Skill Eval'),('add','.'),('commit','-m','Initial commit','--allow-empty'),
 ('branch','-a'),('rev-parse','--abbrev-ref','HEAD'),('rev-parse','HEAD'),
 ('rev-list','--all','--count'),('log','--all','--pretty=format:%H'),
 ('log','--all','--pretty=format:%h %s'),
 ('for-each-ref','refs/heads','--format=%(refname:short) %(objectname)'),
 ('for-each-ref','refs/remotes','--format=%(refname:short) %(objectname)'),
 ('remote','-v'),('status','--porcelain'),
})

def prepare(arguments,cwd,environ):
    if tuple(arguments) not in ALLOWED:
        raise ValueError('Unreviewed Git operation; no clone, transport or arbitrary configuration')
    resolved=cwd.resolve(strict=True)
    if resolved!=cwd or not resolved.is_relative_to(WORKSPACE) or not cwd.is_dir():
        raise ValueError('Git must remain inside the owned scheduler workspace')
    if GIT.is_symlink() or hashlib.sha256(GIT.read_bytes()).hexdigest()!=GIT_SHA256:
        raise ValueError('Selected Git executable changed')
    env={k:environ[k] for k in ('HOME','TMPDIR','LC_ALL','LANG') if k in environ}
    env.update(PATH='/usr/bin:/bin',GIT_EXEC_PATH=EXEC_PATH,GIT_CONFIG_NOSYSTEM='1',
      GIT_CONFIG_SYSTEM='/dev/null',GIT_CONFIG_GLOBAL='/dev/null',GIT_ALLOW_PROTOCOL='',
      GIT_TERMINAL_PROMPT='0',GIT_CONFIG_COUNT='4',GIT_CONFIG_KEY_0='core.hooksPath',
      GIT_CONFIG_VALUE_0='/dev/null',GIT_CONFIG_KEY_1='core.fsmonitor',GIT_CONFIG_VALUE_1='false',
      GIT_CONFIG_KEY_2='commit.gpgSign',GIT_CONFIG_VALUE_2='false',
      GIT_CONFIG_KEY_3='credential.helper',GIT_CONFIG_VALUE_3='')
    return [str(GIT),'--no-pager',*arguments],env

def main():
    argv,env=prepare(sys.argv[1:],Path.cwd(),os.environ)
    os.execve(GIT,argv,env)

if __name__=='__main__':main()
