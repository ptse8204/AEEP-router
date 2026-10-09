"""Run the upstream scripted harness with one captured candidate payload, offline."""
import base64
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from agent_skill_eval.harnesses import FakeHarness
from synthetic_edit import PREFIX, edit

from aeep_toolkit.candidate import identity


def stage(workspace, selected):
    if selected is None:
        return False
    if isinstance(selected,str):
        # Historical single-file fixture input remains supported.
        name,files='format-json',{'SKILL.md':selected.encode()}
    else:
        if (not isinstance(selected,dict) or set(selected)!={'name','sha256','files'}
                or not isinstance(selected['name'],str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',selected['name'])
                or not isinstance(selected['files'],dict)):
            raise ValueError('invalid captured candidate')
        name=selected['name']
        files={key:base64.b64decode(raw,validate=True) for key,raw in selected['files'].items()}
        if identity(files)!=selected['sha256']:
            raise ValueError('captured candidate identity differs inside worker')
    root=workspace/'.fake/skills'/name
    for relative,raw in files.items():
        target=root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:
            handle.write(raw)
    return True


def main():
    request=json.loads(sys.stdin.read(65537))
    if set(request)!={'prompt','skill'} or not isinstance(request['prompt'],str):
        raise ValueError('invalid synthetic trial input')
    with tempfile.TemporaryDirectory(prefix='aeep-ase-trial-') as name:
        workspace=Path(name)
        exposed=stage(workspace,request['skill'])
        payload_sha = None
        if exposed:
            selected_name = request['skill']['name'] if isinstance(request['skill'],dict) else 'format-json'
            selected_root = workspace/'.fake/skills'/selected_name
            payload_sha = identity({str(p.relative_to(selected_root)):p.read_bytes() for p in selected_root.rglob('*') if p.is_file()})
        if request['prompt'].startswith(PREFIX):
            output=edit(request['prompt'],workspace)
        else:
            output,_timing,_stdout,_stderr=FakeHarness(workspace).run(request['prompt'],workspace/'outputs')
        print(json.dumps({'output':output,'candidate_exposed':exposed,'payload_sha256':payload_sha,'uid':os.getuid(),
                          'python_available':bool(sys.executable),'shell_available':bool(shutil.which('sh'))}))


if __name__=='__main__':
    main()
