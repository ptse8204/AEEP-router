"""Record the exact retained service scope after the mount diagnosis."""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from run import HERE, PRIOR, PROJECT, allowed_binds, base, checks
from security import normalize_mounts

import json


def fixture_controls(work):
    allowed = allowed_binds(work)
    target, (source, _) = next(iter(allowed['clickhouse'].items()))
    alias = '/host_mnt' + source
    row = [{'Binds':[f'{alias}:{target}:ro']},
           [{'Type':'bind','Source':alias,'Destination':target,'Mode':'ro','RW':False}],
           {PROJECT+'-private':{}},'101:101']

    def encode(values):
        return ' '.join(json.dumps(value) for value in values)

    corrected, observed = normalize_mounts(encode(row),('clickhouse',),allowed)
    assert json.dumps(source) in corrected and observed['clickhouse']['vm_alias_observed']
    denied = 0
    for key, value in (('Source','/host_mnt/private'+source),('Destination','/other'),
                       ('RW',True),('Mode','rw'),('Type','volume')):
        invalid = deepcopy(row)
        invalid[1][0][key] = value
        try:
            normalize_mounts(encode(invalid),('clickhouse',),allowed)
        except ValueError:
            denied += 1
    for invalid in ([{'Binds':[]}, *row[1:]], [row[0], row[1]*2, *row[2:]]):
        try:
            normalize_mounts(encode(invalid),('clickhouse',),allowed)
        except ValueError:
            denied += 1
    assert denied == 7
    return denied


def main():
    prior_path = PRIOR/'operation-review.json'
    prior = base.load(prior_path)
    result_path = PRIOR/'service-execution/summary.json'
    stop_path = PRIOR/'service-execution/stop-verdict.json'
    outcome = base.load(result_path)
    stop = base.load(stop_path)
    assert base.load(PRIOR/'service-execution/carrier-result.json')['forwarding_counts'] == {'health':2,'export':0,'readback':0}
    work = Path(prior['work'])
    files = [HERE/'run.py',HERE/'security.py',HERE/'prepare.py',prior_path,result_path,stop_path,
             PRIOR/'adaptation-controls.json',PRIOR/'service-execution/receipt-16.json',
             PRIOR/'service-execution/carrier-result.json',PRIOR/'operator-approval.json',
             work/'compose-tmpfs.json',work/'clickhouse-pools.xml',work/'mc/config.json']
    assert all(path.resolve(strict=True)==path for path in files)
    counters = outcome['grant_counters']
    amendment = prior['amendment'] | {
        'amendment_id': HERE.name, 'previous_amendment_digest': base.content_digest(prior['amendment']),
        'limits': prior['amendment']['limits'] | {'max_operations':counters[0]+56},
        'issued_at':datetime.now(UTC).isoformat(),
    }
    review = prior | {
        'purpose':'Restart only the six retained Langfuse service containers and complete the unstarted local receipt export.',
        'original_review_sha256':base.sha(prior_path), 'continuation_plan_id':HERE.name,
        'counters_before':counters, 'containers':stop['owned_container_ids'], 'maximum_operations':counters[0]+56,
        'maximum_additional_operations':56, 'maximum_driver_commands':48, 'amendment':amendment,
        'lifecycle':{
            'retained_only':True,'new_containers':0,'new_volumes':0,'new_networks':0,
            'restarts':['postgres','clickhouse','redis','minio','web','worker'],
            'never_restart':['minio-owner','minio-bucket'],
            'mount_rule':'Exact Compose source and Docker Desktop host_mnt alias only. HostConfig bind, destination and access mode must agree.',
            'carrier':prior['lifecycle']['carrier'],'carrier_limits':prior['lifecycle']['carrier_limits'],
            'egress':prior['lifecycle']['external_probe'],
            'cleanup':'Stop only resumed verified owned processes. Preserve all existing containers, volumes, images and network.',
            'auth':'Consume only existing generated task-local project keys transiently, without printing or persisting new copies.',
        },
        'approval_reason':'The previous attempt started and stopped its services. Restarting them requires exact approval under the operator repeat rule.',
        'service_started':False,'service_assets':prior['service_assets']|{str(path):base.sha(path) for path in files},
    }
    observed = checks(review)
    assert observed['clickhouse']['vm_alias_observed'] is True and observed['minio-bucket']['writable'] is True
    controls = {'passed':True,'binding_controls_denied':fixture_controls(work),
                'all_retained_permission_checks_passed':True,'retained_mounts':observed,
                'old_counters_settled':counters,'started':False}
    with (HERE/'preflight.json').open('x') as out:
        json.dump(controls,out,indent=2);out.write('\n')
    review['service_assets'][str(HERE/'preflight.json')] = base.sha(HERE/'preflight.json')
    path = HERE/'operation-review.json'
    with path.open('x') as out:
        json.dump(review,out,indent=2);out.write('\n')
    print(base.sha(path))


if __name__ == '__main__':
    main()
