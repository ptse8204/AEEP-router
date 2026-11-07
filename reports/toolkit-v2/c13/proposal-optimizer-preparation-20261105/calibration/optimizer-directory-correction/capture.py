"""Let the real AFlow optimizer reach one externally controlled proposal request."""

import asyncio
import hashlib
import json
import os
import shutil
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path


class RequestReady(BaseException):
    """Stop upstream before a provider dispatch or generated graph write."""


class Relay:
    def __init__(self):
        self.request = None

    async def call_with_format(self, prompt, formatter):
        assert self.request is None
        assert type(formatter).__name__ == 'XmlFormatter'
        self.request = formatter.prepare_prompt(prompt)
        assert 0 < len(self.request.encode()) <= 32768
        assert '<modification>' in self.request and '<graph>' in self.request and '<prompt>' in self.request
        raise RequestReady()

    async def __call__(self, _prompt):
        raise RuntimeError('unreviewed optimizer fallback')


async def capture(seed):
    from scripts import optimizer
    from scripts.logs import logger

    logger.console_output = False
    relay = Relay()

    def bind_relay(config):
        assert config == 'aeep-controlled-capture'
        return relay

    root = Path('calibration/aeep_text/workflows')
    initial_directory = root / 'round_1'
    initial_directory.mkdir(parents=True)
    shutil.copyfile('/opt/aeep-baseline.py', initial_directory / 'graph.py')
    (initial_directory / 'prompt.py').write_text(
        '# Extract requested labels. Omit missing labels. '
        'Return {"error": "invalid_input"} when a requested label is repeated.\n',
        encoding='utf-8',
    )
    (root / 'template').mkdir()
    (root / 'template/operator.json').write_text('{}', encoding='utf-8')
    optimizer.create_llm_instance = bind_relay
    flow = optimizer.Optimizer(
        dataset='aeep_text', question_type='qa', opt_llm_config='aeep-controlled-capture',
        exec_llm_config=None, operators=[], sample=1, optimized_path='calibration',
        initial_round=1, max_rounds=1, validation_rounds=1,
    )
    batches = []

    async def observed_grade(current, directory, count, data, initial=False):
        assert current is flow and initial and count == 1 and not data and not batches
        assert flow.graph.__name__ == 'Workflow' and Path(directory) == initial_directory
        batches.append(seed['grade_sha256'])
        score = seed['passed'] / seed['cases']
        row = flow.data_utils.create_result_data(1, score, 0.0, 0.0)
        data.append(row)
        flow.data_utils.save_results(flow.data_utils.get_results_file_path(str(root)), data)
        return score

    flow.evaluation_utils.evaluate_graph = observed_grade
    try:
        await flow._optimize_graph()
    except RequestReady:
        assert relay.request and batches == [seed['grade_sha256']]
        assert not (root / 'round_2/graph.py').exists()
        return {
            'request': relay.request,
            'request_sha256': hashlib.sha256(relay.request.encode()).hexdigest(),
            'initial_grade_sha256': seed['grade_sha256'],
            'upstream_optimizer_executed': True,
            'proposal_requests': 1, 'models': 0, 'generated_code_executed': False,
        }
    raise RuntimeError('optimizer did not reach its bounded proposal callback')


def failure_details(error, stage):
    allowed = ("/opt/aeep-capture.py", "/opt/check_socket_boundary.py", "/opt/aflow-source/scripts/")
    return {
        'status': 'failed', 'stage': stage, 'error_type': type(error).__name__,
        'locations': [
            {'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
            for frame in traceback.extract_tb(error.__traceback__)
            if any(frame.filename == prefix or (prefix.endswith('/') and frame.filename.startswith(prefix))
                   for prefix in allowed)
        ],
    }


def main():
    stage = 'containment'
    try:
        sys.path[:0] = ['/tmp', '/opt', '/opt/aflow-dependencies', '/opt/aflow-source']
        from check_socket_boundary import socket_boundary

        assert (os.geteuid(), os.getegid()) == (65534, 65534)
        assert not os.access('/opt', os.W_OK) and not Path('/var/run/docker.sock').exists()
        status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
        assert status['NoNewPrivs'].strip() == '1' and int(status['CapEff'], 16) == 0
        assert status['Seccomp'].strip() == '2'
        boundary = socket_boundary()
        stage = 'protected grade binding'
        seed = json.loads(Path('/opt/aeep-grade.json').read_bytes())
        assert set(seed) == {'grade_sha256', 'cases', 'passed'}
        assert len(seed['grade_sha256']) == 64 and seed['cases'] == 3
        assert type(seed['passed']) is int and 0 <= seed['passed'] <= seed['cases']
        stage = 'upstream optimizer and formatter'
        with redirect_stdout(sys.stderr):
            result = asyncio.run(capture(seed))
        print(json.dumps({**result, 'status': 'request_ready', 'boundary': boundary}, allow_nan=False))
    except Exception as error:
        print(json.dumps(failure_details(error, stage), allow_nan=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
