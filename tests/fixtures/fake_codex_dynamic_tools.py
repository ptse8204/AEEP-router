"""Offline native client-tool protocol fixture; no inference/authentication."""
import json
import sys

mode = sys.argv[1]
diagnostic_modes = {'reply-stall', 'reject-stall', 'final-stall', 'pending-stall'}
thread_id = 'SYNTHETIC_THREAD_ID' if mode in diagnostic_modes else 'thread'
turn_id = 'SYNTHETIC_TURN_ID' if mode in diagnostic_modes else 'turn'

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
        send({'id': request['id'], 'result': {'thread': {'id': thread_id}}})
    elif method == 'turn/start':
        arguments = {'value': 1}
        call_id = 'call'
        if mode in diagnostic_modes:
            call_id = 'SYNTHETIC_CALLBACK_ID'
            if mode == 'reject-stall':
                arguments['marker'] = 'SYNTHETIC_ARGUMENT_SECRET'
        send({'id': 'call-request', 'method': 'item/tool/call', 'params': {
            'threadId': thread_id, 'turnId': turn_id, 'callId': call_id,
            'namespace': 'task', 'tool': 'fixed', 'arguments': arguments}})
        send({'id': request['id'], 'result': {'turn': {'id': turn_id}}})
        if mode == 'pending-stall':
            # The parent answers this ordinary request while the dynamic callback
            # remains blocked, then times out and interrupts the open turn.
            continue
        if mode in {'reply-stall', 'reject-stall', 'final-stall'}:
            reply = json.loads(sys.stdin.readline())
            send({'method': 'callback/replied', 'params': {
                'success': isinstance(reply.get('result'), dict)
                and reply['result'].get('success') is True,
                'detail': 'SYNTHETIC_CALLBACK_ERROR_SECRET' if mode == 'reject-stall' else None}})
            send({'method': 'item/completed', 'params': {'threadId': thread_id, 'turnId': turn_id,
                'item': {'id': 'SYNTHETIC_ITEM_ID', 'type': 'dynamicToolCall',
                         'namespace': 'task', 'tool': 'fixed', 'status': 'completed'}}})
            if mode == 'final-stall':
                send({'method': 'item/completed', 'params': {'threadId': thread_id, 'turnId': turn_id,
                    'item': {'id': 'SYNTHETIC_FINAL_ID', 'type': 'agentMessage',
                             'phase': 'final_answer', 'text': 'SYNTHETIC_FINAL_TEXT_SECRET'}}})
            # Stay alive until the adapter sends turn/interrupt. Deliberately do
            # not send turn/completed: callback evidence alone is not turn success.
            continue
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
    elif method == 'turn/interrupt' and mode in diagnostic_modes:
        # Emit a terminal cleanup notification after the adapter has timed out.
        # Its returned diagnostic must preserve the pre-interrupt snapshot.
        send({'method': 'turn/completed', 'params': {'threadId': thread_id,
            'turn': {'id': turn_id, 'status': 'interrupted'}}})
        send({'id': request['id'], 'result': {}})
    else:
        send({'id': request['id'], 'result': {}})
