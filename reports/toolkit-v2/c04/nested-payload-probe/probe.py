"""Run the pinned install/hash seam on synthetic files inside the existing sandbox."""

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'integrations/toolkit'))
import stack  # noqa: E402

RUNTIME = Path('/private/tmp/aeep-ase-c04-tt14mj6r/rebuild')
OUTPUT = Path(__file__).resolve().parent
CHILD = r'''
import hashlib, json
from pathlib import Path
from agent_skill_eval.models import AgentType
from agent_skill_eval.skills import SkillInstaller
source = Path('candidate')
source.mkdir()
(source / 'SKILL.md').write_text('---\nname: candidate\ndescription: synthetic payload test\n---\nNo agent calls.\n')
for path in ('evals/top.txt', 'resources/evals/nested.txt', 'resources/.git/config', 'resources/__pycache__/marker.txt'):
    target = source / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('synthetic-marker-v1\n')
installer = SkillInstaller(source)
hash_before = installer.content_hash()
(source / 'resources/evals/nested.txt').write_text('synthetic-marker-v2\n')
hash_after = installer.content_hash()
installed = installer.install(Path('workspace'), AgentType.FAKE)
files = {str(p.relative_to(installed)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(installed.rglob('*')) if p.is_file()}
result = dict(hash_before=hash_before, hash_after=hash_after, installed_files=files,
              top_level_evals_excluded=not (installed / 'evals').exists(),
              nested_evals_copied=(installed / 'resources/evals/nested.txt').exists(),
              nested_git_copied=(installed / 'resources/.git/config').exists(),
              nested_cache_copied=(installed / 'resources/__pycache__/marker.txt').exists())
assert hash_before == hash_after
assert result['top_level_evals_excluded']
assert result['nested_evals_copied'] and result['nested_git_copied'] and result['nested_cache_copied']
print(json.dumps(result))
'''


def main():
    selected = stack.manifest()
    stack.verify_runtime(RUNTIME, selected)
    scratch = Path(tempfile.mkdtemp(prefix='aeep-ase-nested-payload-', dir='/tmp')).resolve()
    result = {'status': 'started', 'scratch': str(scratch), 'evidence_kind': 'synthetic',
              'evaluator': selected['evaluator'], 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        prefix, env = stack.sandbox(scratch, RUNTIME)
        result['sandbox_checks'] = stack.probe(prefix, env, scratch)
        result['observed'] = json.loads(stack.command([*prefix, '-c', CHILD], cwd=scratch, env=env, timeout=30))
        result['status'] = 'finding_reproduced'
        result['finding'] = 'Upstream recursively excludes nested evals/.git/__pycache__ from content_hash, but install excludes those directories only at the top level. Installed payload can change without the reported skill hash changing.'
        result['scope'] = 'Synthetic local payload/hash conformance only; no real answers, credentials, agent, containers or network.'
        shutil.rmtree(scratch)
        result['scratch_removed'] = True
    finally:
        (OUTPUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
