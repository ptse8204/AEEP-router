"""Pinned ASE coordinator child: scheduling/grading stay upstream; dispatch is stdio."""
import contextlib
import json
import sys
from pathlib import Path

from agent_skill_eval.harnesses import HARNESSES, FakeHarness
from agent_skill_eval.models import AgentType, TimingData
from agent_skill_eval.runner import EvalRunner

channel = sys.stdout


class ControlledFixtureHarness(FakeHarness):
    def run(self, prompt, output_dir):
        treatment = any((self.workspace / '.fake/skills').glob('*/SKILL.md'))
        channel.write(json.dumps({'kind': 'trial', 'prompt': prompt, 'treatment': treatment}) + '\n')
        channel.flush()
        response = json.loads(sys.stdin.readline(65537))
        if set(response) != {'output'} or not isinstance(response['output'], str):
            raise ValueError('controlled dispatch failed')
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir/'stdout.log').write_text(response['output'])
        (output_dir/'stderr.log').write_text('')
        # Upstream requires integer usage fields; no usage from these placeholders is imported.
        return response['output'], TimingData(exit_code=0), response['output'], ''


if __name__ == '__main__':
    fixture, output = map(Path, sys.argv[1:])
    HARNESSES[AgentType.FAKE] = ControlledFixtureHarness
    with contextlib.redirect_stdout(sys.stderr):
        runner = EvalRunner(fixture, fixture/'evals/evals.json', output, [AgentType.FAKE],
                            concurrency=1, with_baseline=True, grader_model='', agent_max_retries=0)
        runner.run()
    channel.write(json.dumps({'kind': 'done'}) + '\n')
    channel.flush()
