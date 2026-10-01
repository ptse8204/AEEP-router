"""Offline native client-tool protocol fixture; no inference/authentication."""
import json
import sys

mode = sys.argv[1]

def send(value):
    print(json.dumps(value), flush=True)

for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if 'id' not in request:
        continue
    if method == 'initialize':
        send({'id': request['id'], 'result': {'userAgent': 'fixture/1'}})
    elif method == 'thread/start':
        assert request['params']['dynamicTools'][0]['name'] == 'task'
        send({'id': request['id'], 'result': {'thread': {'id': 'thread'}}})
    elif method == 'turn/start':
        send({'id': 'call-request', 'method': 'item/tool/call', 'params': {
            'threadId': 'thread', 'turnId': 'turn', 'callId': 'call',
            'namespace': 'task', 'tool': 'fixed', 'arguments': {'value': 1}}})
        send({'id': request['id'], 'result': {'turn': {'id': 'turn'}}})
        if mode in {'eof', 'early-terminal'}:
            entered = json.loads(sys.stdin.readline())
            assert entered.get('method') == 'fixture/entered'
            if mode == 'eof':
                break
            send({'id': entered['id'], 'result': {}})
        if mode == 'early-terminal':
            send({'method': 'turn/completed', 'params': {'threadId': 'thread',
                  'turn': {'id': 'turn', 'status': 'completed'}}})
        else:
            reply = json.loads(sys.stdin.readline())
            send({'method': 'callback/replied', 'params': {'success': reply.get('result', {}).get('success')}})
            send({'method': 'item/completed', 'params': {'threadId': 'thread', 'turnId': 'turn',
                'item': {'id': 'call', 'type': 'dynamicToolCall', 'namespace': 'task', 'tool': 'fixed', 'status': 'completed'}}})
            send({'method': 'item/completed', 'params': {'threadId': 'thread', 'turnId': 'turn',
                'item': {'type': 'agentMessage', 'phase': 'final_answer', 'text': '{"completed":true}'}}})
            send({'method': 'turn/completed', 'params': {'threadId': 'thread',
                  'turn': {'id': 'turn', 'status': 'completed'}}})
    else:
        send({'id': request['id'], 'result': {}})
