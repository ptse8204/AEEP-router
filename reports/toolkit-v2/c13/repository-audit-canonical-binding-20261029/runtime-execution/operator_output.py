"""Keep the default raw protocol separate from reviewed diagnostic envelopes."""
import base64

FIELDS={'exit_code','statuses','archive_sha256','python','pytest'}

def observation(output,profile):
    if profile=='default':
        if (not isinstance(output,dict) or set(output)!=FIELDS or type(output['exit_code']) is not int
                or output['exit_code'] not in range(6) or not isinstance(output['statuses'],dict)
                or len(output['statuses'])>10000 or any(not isinstance(n,str) or s not in ('PASSED','FAILED','ERROR','SKIPPED','XFAIL') for n,s in output['statuses'].items())):
            raise ValueError('Default observer raw protocol mismatch')
        return output
    if profile!='operator' or not isinstance(output,dict) or len(output)!=2 or 'failure_log_tail_b64' not in output:
        raise ValueError('Operator diagnostic envelope mismatch')
    kind='collection' if 'collection' in output else 'evaluation'
    if set(output)!={kind,'failure_log_tail_b64'}:raise ValueError('Mixed observer roles')
    value=output[kind]
    fields={'exit_code','archive_sha256','python','pytest'}|({'native_ids','selected_ids'} if kind=='collection' else {'statuses'})
    if not isinstance(value,dict) or set(value)!=fields:raise ValueError('Native diagnostic protocol mismatch')
    if type(value['exit_code']) is not int or value['exit_code'] not in range(6):raise ValueError('Invalid exit status')
    tail=base64.b64decode(output['failure_log_tail_b64'],validate=True)
    if len(tail)>8192 or value['exit_code']==0 and tail:raise ValueError('Failure-log retention bound exceeded')
    if kind=='collection':
        for key in ('native_ids','selected_ids'):
            nodes=value[key]
            if (not isinstance(nodes,list) or len(nodes)>10000 or any(not isinstance(n,str) or not n.strip() or not n.isprintable() or len(n.encode('utf-8'))>8192 for n in nodes) or len(set(nodes))!=len(nodes)):
                raise ValueError('Collection identity protocol failed')
        if not set(value['selected_ids'])<=set(value['native_ids']):raise ValueError('Collection selection scope failed')
    return value
