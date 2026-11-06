"""Normalize exact Docker Desktop aliases after validating both mount observations."""

import json


def decode(line):
    decoder = json.JSONDecoder()
    while line.strip():
        value, end = decoder.raw_decode(line.lstrip())
        yield value
        line = line.lstrip()[end:]


def normalize_mounts(text, services, allowed_binds):
    rows = []
    observed = {}
    for service, line in zip(services, text.splitlines(), strict=True):
        host, mounts, networks, user = tuple(decode(line))
        declared = allowed_binds.get(service, {})
        seen = set()
        for mount in mounts:
            if mount.get('Type') != 'bind':
                continue
            target = mount['Destination']
            if target in seen or target not in declared:
                raise ValueError(f'Unexpected bind target for {service}')
            expected, writable = declared[target]
            source = mount['Source']
            mode = 'rw' if writable else 'ro'
            if (source not in {expected, '/host_mnt' + expected}
                    or mount['RW'] is not writable or mount['Mode'] != mode
                    or f'{source}:{target}:{mode}' not in (host.get('Binds') or [])):
                raise ValueError(f'Bind source or mode differs for {service}')
            observed[service] = {'destination': target, 'vm_alias_observed': source != expected,
                                 'writable': writable}
            seen.add(target)
            mount['Source'] = expected
        if seen != set(declared):
            raise ValueError(f'Missing reviewed bind for {service}')
        rows.append(' '.join(json.dumps(item, separators=(',', ':')) for item in (host, mounts, networks, user)))
    return '\n'.join(rows), observed
