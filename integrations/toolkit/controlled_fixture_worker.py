"""Execute upstream FakeHarness inside one disposable, network-disabled container."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from agent_skill_eval.harnesses import FakeHarness

request = json.loads(sys.stdin.read(65537))
if set(request) != {'prompt', 'skill'} or not isinstance(request['prompt'], str):
    raise ValueError('invalid fixed fixture input')
with tempfile.TemporaryDirectory(prefix='aeep-ase-trial-') as name:
    workspace = Path(name)
    if request['skill'] is not None:
        skill = workspace/'.fake/skills/format-json/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text(request['skill'])
    exposed = any((workspace/'.fake/skills').glob('*/SKILL.md'))
    output, _timing, _stdout, _stderr = FakeHarness(workspace).run(request['prompt'], workspace/'outputs')
    print(json.dumps({'output': output, 'candidate_exposed': exposed,
                      'uid': os.getuid(), 'python_available': bool(sys.executable),
                      'shell_available': bool(shutil.which('sh'))}))
