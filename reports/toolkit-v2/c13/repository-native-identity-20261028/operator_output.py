"""Separate collection diagnostics from evaluations; bound public log retention."""
import base64


def observation(output):
    if not isinstance(output, dict) or len(output) != 2 or 'failure_log_tail_b64' not in output:
        raise ValueError('Operator observer envelope mismatch')
    kind = 'collection' if 'collection' in output else 'evaluation'
    if set(output) != {kind, 'failure_log_tail_b64'}:
        raise ValueError('Observer reply has mixed or unrecognized roles')
    value = output[kind]
    fields = {'exit_code', 'archive_sha256', 'python', 'pytest'}
    fields |= {'native_ids', 'selected_ids'} if kind == 'collection' else {'statuses'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('Native observer protocol mismatch')
    tail = base64.b64decode(output['failure_log_tail_b64'], validate=True)
    if len(tail) > 8192 or type(value['exit_code']) is not int or value['exit_code'] not in range(6) or (value['exit_code'] == 0 and tail):
        raise ValueError('Public failure tail or exit code exceeds authority')
    if kind == 'collection':
        for key in ('native_ids', 'selected_ids'):
            nodes = value[key]
            if (not isinstance(nodes, list) or len(nodes) > 10000
                    or any(not isinstance(n, str) or not n or not n.isprintable() or len(n.encode('utf-8')) > 8192 for n in nodes)
                    or len(set(nodes)) != len(nodes)):
                raise ValueError('Invalid collection identities')
        if not set(value['selected_ids']) <= set(value['native_ids']):
            raise ValueError('Selected identities absent from native collection')
    return value
