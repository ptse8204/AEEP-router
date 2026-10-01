"""Pinned zero-model scripted JSONL callback peer; no credentials or native claims."""
import json
import sys

arguments = json.loads(sys.argv[1]) if len(sys.argv) == 2 else {}
assert isinstance(arguments, dict) and len(json.dumps(arguments).encode()) <= 4096
namespace = tool = None
for line in sys.stdin:
    message = json.loads(line)
    method = message.get('method')
    if method == 'initialize':
        print(json.dumps({'id': message['id'], 'result': {'userAgent': 'composed-fixture/1'}}), flush=True)
    elif method == 'thread/start':
        declarations = message['params']['dynamicTools']
        assert len(declarations) == 1 and len(declarations[0]['tools']) == 1
        namespace = declarations[0]['name']
        tool = declarations[0]['tools'][0]['name']
        print(json.dumps({'id': message['id'], 'result': {'thread': {'id': 'fixture-thread'}}}), flush=True)
    elif method == 'fixture/callback':
        print(json.dumps({'id': 'fixture-call-request', 'method': 'item/tool/call', 'params': {
            'threadId': 'fixture-thread', 'turnId': 'fixture-turn', 'callId': 'fixture-call',
            'namespace': namespace, 'tool': tool, 'arguments': arguments}}), flush=True)
        print(json.dumps({'id': message['id'], 'result': {'turn': {'id': 'fixture-turn'}}}), flush=True)
    elif message.get('id') == 'fixture-call-request':
        print(json.dumps({'method': 'fixture/callback-result', 'params': {
            'response_success': message.get('result', {}).get('success') is True}}), flush=True)
