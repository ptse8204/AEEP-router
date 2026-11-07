"""Let the real AFlow optimizer reach one externally controlled proposal request."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path


CHOICES = frozenset(('reject_duplicate', 'keep_first'))


def parse_reply(text):
    reply = json.loads(text)
    assert set(reply) == {'xml'}
    match = re.fullmatch(
        r"<modification>([A-Za-z0-9 ,.'()_-]{1,160})</modification>\s*"
        r"<graph>(reject_duplicate|keep_first)</graph>\s*<prompt></prompt>",
        reply['xml'],
    )
    if match is None:
        raise ValueError('reply is outside the reviewed graph inventory')
    return reply['xml'], match[1], match[2]


def output_digest(outputs):
    return hashlib.sha256(json.dumps(outputs, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()).hexdigest()


async def cycle(seed, request, public, certificates):
    from scripts import optimizer
    from scripts.logs import logger

    logger.console_output = False
    xml, modification, selection = parse_reply(request['text'])
    assert selection in CHOICES
    calls = 0
    output_sha = None

    class Relay:
        async def call_with_format(self, prompt, formatter):
            nonlocal calls
            assert calls == 0
            calls += 1
            formatted = formatter.prepare_prompt(prompt)
            assert hashlib.sha256(formatted.encode()).hexdigest() == request['request_sha256']
            valid, fields = formatter.validate_response(xml)
            assert valid and fields == {'modification': modification, 'graph': selection, 'prompt': ''}
            return fields

        async def __call__(self, _prompt):
            raise RuntimeError('unreviewed optimizer fallback')

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
    chosen_directory = root / 'round_2'
    variants = Path('/opt/aeep-variants.py').read_text()

    def write_reviewed_graph(directory, response, round_id, dataset):
        assert Path(directory) == chosen_directory and round_id == 2 and dataset == 'aeep_text'
        assert response == {'modification': modification, 'graph': selection, 'prompt': ''}
        marker = 'POLICY = "initial"'
        assert variants.count(marker) == 1
        (chosen_directory / 'graph.py').write_text(variants.replace(marker, 'POLICY = ' + repr(selection)), encoding='utf-8')
        (chosen_directory / 'prompt.py').write_text('', encoding='utf-8')

    async def observed_grade(current, directory, count, data, initial=False):
        nonlocal output_sha
        assert current is flow and count == 1 and flow.graph.__name__ == 'Workflow'
        if initial:
            assert Path(directory) == initial_directory and not data and not batches
            score = seed['passed'] / seed['cases']
        else:
            assert Path(directory) == chosen_directory and len(data) == 1 and batches == ['initial']
            cert = certificates[selection]
            assert len(public) == cert['cases'] == seed['cases']
            outputs = [await flow.graph()(**case['input']) for case in public]
            output_sha = output_digest(outputs)
            assert output_sha == cert['outputs_sha256']
            score = cert['passed'] / cert['cases']
        batches.append('initial' if initial else 'selected')
        row = flow.data_utils.create_result_data(len(batches), score, 0.0, 0.0)
        data.append(row)
        flow.data_utils.save_results(flow.data_utils.get_results_file_path(str(root)), data)
        return score

    flow.evaluation_utils.evaluate_graph = observed_grade
    flow.graph_utils.write_graph_files = write_reviewed_graph
    score = await flow._optimize_graph()
    assert calls == 1 and batches == ['initial', 'selected'] and output_sha
    experience = json.loads((chosen_directory / 'experience.json').read_text())
    assert experience['father node'] == 1 and experience['modification'] == modification
    assert experience['before'] == seed['passed'] / seed['cases'] and experience['after'] == score
    assert experience['succeed'] is (score > experience['before'])
    return {
        'request_sha256': request['request_sha256'], 'initial_grade_sha256': seed['grade_sha256'],
        'upstream_optimizer_executed': True, 'proposal_requests': 1, 'models_in_guest': 0,
        'generated_code_executed': False, 'policy': selection, 'initial_score': experience['before'],
        'selected_score': score, 'outputs_sha256': output_sha,
        'upstream_experience_updated': True, 'engineering_only': True,
    }


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
        raw = sys.stdin.buffer.read(8193)
        assert 0 < len(raw) <= 8192
        request = json.loads(raw)
        assert set(request) == {'request_sha256', 'text'} and len(request['request_sha256']) == 64
        public = json.loads(Path('/opt/aeep-public-cases.json').read_bytes())['cases']
        certificates = json.loads(Path('/opt/aeep-certificates.json').read_bytes())
        assert set(certificates) == CHOICES
        with redirect_stdout(sys.stderr):
            result = asyncio.run(cycle(seed, request, public, certificates))
        print(json.dumps({**result, 'status': 'cycle_complete', 'boundary': boundary}, allow_nan=False))
    except Exception as error:
        print(json.dumps(failure_details(error, stage), allow_nan=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
