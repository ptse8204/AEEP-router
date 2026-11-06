"""Connect EvoAgentX's real planner to a single, externally controlled reply."""

import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path

MAX_BYTES = 32_768


def encode(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def checked(condition, code):
    if not condition:
        raise ValueError(code)


def no_duplicates(pairs):
    result = dict(pairs)
    checked(len(result) == len(pairs), 'duplicate JSON field')
    return result


def bounded_text(value):
    return isinstance(value, str) and len(value.encode()) <= 512 and all(
        character.isprintable() and character not in '{}[]`' for character in value
    )


def normalize(text, ports):
    """Reject model-supplied component constructors before the upstream parser."""
    checked(isinstance(text, str) and 0 < len(text.encode()) <= MAX_BYTES, 'response size')
    plan = json.loads(text, object_pairs_hook=no_duplicates)
    checked(isinstance(plan, dict) and set(plan) == {'sub_tasks'}, 'response fields')
    nodes = plan['sub_tasks']
    checked(isinstance(nodes, list) and len(nodes) == len(ports), 'node count')
    names = set()
    for node in nodes:
        checked(isinstance(node, dict) and set(node) in (
            {'name', 'description', 'inputs', 'outputs'},
            {'name', 'description', 'reason', 'inputs', 'outputs'},
        ), 'node fields')
        name = node['name']
        checked(isinstance(name, str) and name in ports and name not in names, 'unknown or duplicate node')
        names.add(name)
        checked(bounded_text(node['description']) and bounded_text(node.get('reason', '')), 'node text')
        for side, role in (('inputs', 'input'), ('outputs', 'output')):
            values = node[side]
            checked(isinstance(values, list) and len(values) == 1, 'port count')
            port = values[0]
            checked(isinstance(port, dict) and set(port) == {'name', 'type', 'description'}, 'port fields')
            checked(port['name'] == ports[name][role] and port['type'] == 'string', 'unreviewed port')
            checked(bounded_text(port['description']), 'port text')
    # Emit reviewed identifier and port shapes to EvoAgentX. Model descriptions are not executable.
    return encode(plan).decode()


class RequestReady(BaseException):
    pass


def run(case, reply=None):
    from evoagentx.workflow.workflow_generator import WorkFlowGenerator
    from evoagentx.agents.task_planner import TaskPlanner
    from evoagentx.models.base_model import BaseLLM
    from evoagentx.models.model_configs import LLMConfig

    class Relay(BaseLLM):
        def init_model(self):
            self.calls = 0

        def formulate_messages(self, prompts, system_messages=None):
            checked(len(prompts) == 1 and len(system_messages or []) <= 1, 'prompt count')
            prefix = [{'role': 'system', 'content': system_messages[0]}] if system_messages else []
            return [prefix + [{'role': 'user', 'content': prompts[0]}]]

        def single_generate(self, messages, **kwargs):
            checked(self.calls == 0 and not kwargs, 'unexpected relay call')
            self.calls += 1
            checked(len(encode(messages)) <= MAX_BYTES, 'prompt size')
            self.messages = messages
            self.request_sha256 = digest(messages)
            if reply is None:
                raise RequestReady()
            checked(reply['request_sha256'] == self.request_sha256, 'request digest mismatch')
            return normalize(reply['text'], case['ports'])

        def batch_generate(self, batch_messages, **kwargs):
            checked(len(batch_messages) == 1, 'unexpected batch')
            return [self.single_generate(batch_messages[0], **kwargs)]

        async def single_generate_async(self, messages, **kwargs):
            raise ValueError('unexpected asynchronous relay call')

    relay = Relay(LLMConfig(llm_type='reviewed_aep_relay', model='external-reviewed-worker'))
    generator = WorkFlowGenerator.model_construct(task_planner=TaskPlanner(llm=relay))
    try:
        plan = generator.generate_plan(goal=case['goal'], suggestion=case['suggestion'])
    except RequestReady:
        return {'status': 'request_ready', 'messages': relay.messages, 'request_sha256': relay.request_sha256,
                'relay_calls': relay.calls, 'models': 0}
    checked(reply is not None and relay.calls == 1, 'unbound planner result')
    graph = generator.build_workflow_from_plan(case['goal'], plan)
    nodes = sorted(node.name for node in graph.nodes)
    edges = sorted((edge.source, edge.target) for edge in graph.edges)
    expected = sorted((source, target) for source, output in case['ports'].items()
                      for target, input_ in case['ports'].items() if output['output'] == input_['input'])
    checked(nodes == sorted(case['ports']) and edges == expected, 'graph differs from reviewed ports')
    return {'status': 'graph_ready', 'nodes': nodes, 'edges': edges,
            'request_sha256': relay.request_sha256, 'generated_code_executed': False}


def main():
    sys.path[:0] = ['/opt', '/opt/evoagentx-dependencies', '/opt/evoagentx-source']
    from check_socket_boundary import socket_boundary

    checked((os.geteuid(), os.getegid()) == (65534, 65534), 'runtime uid')
    checked(not Path('/var/run/docker.sock').exists() and not os.access('/opt', os.W_OK), 'runtime mounts')
    boundary = socket_boundary()
    case = json.loads(Path('/opt/aeep-reviewed-case.json').read_bytes())
    args = sys.argv[1:]
    checked(args in (['prepare'], ['finish']), 'mode')
    reply = None
    if args == ['finish']:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1025)
        checked(len(raw) <= MAX_BYTES + 1024, 'reply envelope size')
        reply = json.loads(raw, object_pairs_hook=no_duplicates)
        checked(isinstance(reply, dict) and set(reply) == {'request_sha256', 'text'}, 'reply envelope')
    try:
        with contextlib.redirect_stdout(sys.stderr):
            outcome = run(case, reply)
    except Exception as exc:
        print(json.dumps({'status': 'rejected', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
    print(json.dumps({**outcome, 'boundary': boundary}))


if __name__ == '__main__':
    main()
