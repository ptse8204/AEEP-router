"""Unwrap exactly the approved public-test envelope, preserving stock evaluation."""
import base64

def evaluation(output):
    if not isinstance(output,dict) or set(output)!={'evaluation','failure_log_tail_b64'}:
        raise ValueError('Operator observer envelope mismatch')
    value=output['evaluation']
    if not isinstance(value,dict) or set(value)!={'exit_code','statuses','archive_sha256','python','pytest'}:
        raise ValueError('Stock evaluation mismatch')
    tail=base64.b64decode(output['failure_log_tail_b64'],validate=True)
    if len(tail)>8192 or (value['exit_code']==0 and tail):
        raise ValueError('Public failure tail exceeds retention authority')
    return value
