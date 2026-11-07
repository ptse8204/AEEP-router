"""Let the real AFlow optimizer reach one externally controlled proposal request."""

import asyncio
import hashlib
import json
import os
import shutil
import sys
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
        assert 0 < len(prompt.encode()) <= 32768
        self.request = prompt
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
    initial = root / 'round_1'
    initial.mkdir(parents=True)
    shutil.copyfile('/opt/aeep-baseline.py', initial / 'graph.py')
    (initial / 'prompt.py').write_text(
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
        assert flow.graph.__name__ == 'Workflow' and Path(directory) == initial
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


def main():
    sys.path[:0] = ['/tmp', '/opt', '/opt/aflow-dependencies', '/opt/aflow-source']
    from check_socket_boundary import socket_boundary

    assert (os.geteuid(), os.getegid()) == (65534, 65534)
    assert not os.access('/opt', os.W_OK) and not Path('/var/run/docker.sock').exists()
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    assert status['NoNewPrivs'].strip() == '1' and int(status['CapEff'], 16) == 0
    assert status['Seccomp'].strip() == '2'
    boundary = socket_boundary()
    seed = json.loads(Path('/opt/aeep-grade.json').read_bytes())
    assert set(seed) == {'grade_sha256', 'cases', 'passed'}
    assert len(seed['grade_sha256']) == 64 and seed['cases'] == 3
    assert type(seed['passed']) is int and 0 <= seed['passed'] <= seed['cases']
    with redirect_stdout(sys.stderr):
        result = asyncio.run(capture(seed))
    print(json.dumps({**result, 'boundary': boundary}, allow_nan=False))


if __name__ == '__main__':
    main()
