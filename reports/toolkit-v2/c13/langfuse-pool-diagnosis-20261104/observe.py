"""Extract narrow startup facts from the newly stopped namespace."""
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

review = json.loads(Path(sys.argv[1]).read_bytes())
command = [review['docker'], '--config', review['docker_config'], '--host',
           'unix://' + review['docker_socket']]
template = ('{{json .Id}} {{json .Name}} {{json .Image}} '
            '{{json (index .Config.Labels "com.aeep.engineering.owner")}} '
            '{{json .State.Running}} {{json .State.ExitCode}} {{json .State.OOMKilled}} '
            '{{if .State.Health}}{{json .State.Health.Status}} {{range .State.Health.Log}}'
            '{{.ExitCode}} {{end}}{{else}}null{{end}}')
rows = subprocess.check_output(
    [*command, 'inspect', '--format', template, *review['owned_container_ids'].values()],
    stderr=subprocess.DEVNULL, timeout=10,
).decode().splitlines()
observations = {}
for (service, expected_id), row in zip(review['owned_container_ids'].items(), rows, strict=True):
    ident, name, image, owner, running, exit_code, oom, health, *probes = [
        json.loads(x) for x in row.split()
    ]
    assert ident == expected_id and owner == review['project']
    assert name == '/' + owner + '-' + service and not running
    assert image in review['service_image_allowed_ids'][service]
    observations[service] = dict(id=ident, exit_code=exit_code, oom_killed=oom,
                                 health_status=health, health_exit_codes=probes)
logs = {}
for suffix in ('err.log', 'log'):
    path = '/var/log/clickhouse-server/clickhouse-server.' + suffix
    cid = review['owned_container_ids']['clickhouse']
    with subprocess.Popen([*command, 'cp', f'{cid}:{path}', '-'],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        try:
            assert process.stdout is not None
            with tarfile.open(fileobj=process.stdout, mode='r|') as tar:
                item = tar.next()
                assert item is not None and item.isfile() and item.size <= 2 * 1024**2
                body_file = tar.extractfile(item)
                assert body_file is not None
                body = body_file.read()
                assert len(body) == item.size
        finally:
            if process.poll() is None:
                process.terminate()
    content = body.decode(errors='replace')
    categories = (
        'backgroundschedulepool', 'global thread pool', 'failed to allocate',
        'permission denied', 'readonly', 'read-only file system', 'fatal',
        'not enough threads', 'cannot allocate memory', 'ready for connections',
        'listening for http', 'mergetree', 'invalidconfigparameter',
        'config_parameter_constraint_violation', 'number_of_free_entries_in_pool',
        'background_merges_mutations_concurrency_ratio', 'background_pool_size',
        'background_schedule_pool_size', 'processing configuration file',
        'zz-aeep-engineering-pools.xml',
    )
    relation = re.findall(
        r'(number_of_free_entries_in_pool[a-z_]+).*?\((\d+)\).*?\((\d+)\)',
        content, flags=re.IGNORECASE,
    )
    logs[suffix] = dict(
        bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
        error_codes=sorted({int(x) for x in re.findall(r'\bCode:\s*(\d+)', content)}),
        thread_counts=sorted({int(x) for x in re.findall(r'\b(\d+)\s+threads\b', content)}),
        categories=[x for x in categories if x in content.lower()],
        pool_constraints=sorted(set(relation)),
    )
print(json.dumps({'stopped': observations, 'clickhouse': logs, 'raw_content_retained': False}))
