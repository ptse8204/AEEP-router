"""Reviewable adaptation of upstream Compose; imports never contact Docker."""
from pathlib import Path

PROJECT = 'aeep-langfuse-engineering-20261104'
LABEL = 'com.aeep.engineering.owner'
PORT = 39067
SECRETS = ('postgres', 'redis', 'clickhouse', 'minio', 'salt', 'encryption',
           'nextauth', 'public', 'secret', 'password')
SERVICES = ('minio-owner', 'postgres', 'clickhouse', 'redis', 'minio',
            'minio-bucket', 'web', 'worker')


def compose(images, work, secrets):
    """Only new local secrets are substituted, after separate service approval."""
    assert set(secrets) == set(SECRETS)
    work = Path(work)
    common = dict(restart='no', pull_policy='never', read_only=True,
                  cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                  networks=['private'], pids_limit=256, cpus=1.0,
                  labels={LABEL: PROJECT},
                  logging={'driver': 'json-file', 'options': {'max-size': '1m', 'max-file': '1'}})

    def service(image, memory, **kw):
        return {**common, 'image': images[image], 'mem_limit': str(memory)+'m',
                'memswap_limit': str(memory)+'m',
                'container_name': PROJECT+'-'+kw.pop('name'), **kw}

    health = lambda command: {'test': ['CMD', *command], 'interval': '2s',
                             'timeout': '2s', 'retries': 20, 'start_period': '3s'}
    environment = {
        'NEXTAUTH_URL': f'http://127.0.0.1:{PORT}',
        'DATABASE_URL': 'postgresql://postgres:'+secrets['postgres']+'@postgres:5432/langfuse',
        'SALT': secrets['salt'], 'ENCRYPTION_KEY': secrets['encryption'],
        'TELEMETRY_ENABLED': 'false', 'LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES': 'false',
        'LANGFUSE_IN_APP_AGENT_ENABLED': 'false', 'LANGFUSE_REQUIRE_FIPS': 'false',
        'LANGFUSE_S3_BATCH_EXPORT_ENABLED': 'false', 'LANGFUSE_USE_AZURE_BLOB': 'false',
        'LANGFUSE_USE_OCI_NATIVE_OBJECT_STORAGE': 'false',
        'CLICKHOUSE_MIGRATION_URL': 'clickhouse://clickhouse:9000',
        'CLICKHOUSE_URL': 'http://clickhouse:8123', 'CLICKHOUSE_USER': 'clickhouse',
        'CLICKHOUSE_PASSWORD': secrets['clickhouse'], 'CLICKHOUSE_CLUSTER_ENABLED': 'false',
        'REDIS_HOST': 'redis', 'REDIS_PORT': '6379', 'REDIS_AUTH': secrets['redis'],
        'REDIS_TLS_ENABLED': 'false', 'NODE_OPTIONS': '--max-old-space-size=640',
        'LANGFUSE_S3_EVENT_UPLOAD_BUCKET': 'langfuse',
        'LANGFUSE_S3_EVENT_UPLOAD_REGION': 'auto',
        'LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID': 'aeepminio',
        'LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY': secrets['minio'],
        'LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT': 'http://minio:9000',
        'LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE': 'true',
        'LANGFUSE_S3_EVENT_UPLOAD_PREFIX': 'events/',
        'LANGFUSE_S3_MEDIA_UPLOAD_BUCKET': 'langfuse',
        'LANGFUSE_S3_MEDIA_UPLOAD_REGION': 'auto',
        'LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID': 'aeepminio',
        'LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY': secrets['minio'],
        'LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT': 'http://minio:9000',
        'LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE': 'true',
        'LANGFUSE_S3_MEDIA_UPLOAD_PREFIX': 'media/',
        'LANGFUSE_AI_API_KEY': '', 'LANGFUSE_AI_PROVIDER': '', 'LANGFUSE_AI_MODEL': '',
        'LANGFUSE_AI_BASE_URL': '', 'LANGFUSE_EE_LICENSE_KEY': '',
        'SMTP_CONNECTION_URL': '', 'EMAIL_FROM_ADDRESS': '',
        'LANGFUSE_INGESTION_CLICKHOUSE_WRITE_INTERVAL_MS': '1000',
        'LANGFUSE_INGESTION_QUEUE_DELAY_MS': '1000',
    }
    tmp = {'/tmp': 'rw,noexec,nosuid,size=64m'}
    root_caps = ['CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'SETUID', 'SETGID']
    volumes = lambda data: [data+':/data']
    services = {
        # Ownership of this brand-new volume root only; no recursive chown.
        'minio-owner': service('chainguard-minio', 64, name='minio-owner', user='0:0',
            entrypoint=['/usr/bin/chown'], command=['65532:65532', '/data'],
            cap_add=['CHOWN'], volumes=volumes('minio-data'), tmpfs=tmp),
        'postgres': service('library-postgres', 512, name='postgres', cap_add=root_caps,
            environment={'POSTGRES_USER': 'postgres', 'POSTGRES_DB': 'langfuse',
                         'POSTGRES_PASSWORD': secrets['postgres'], 'TZ': 'UTC', 'PGTZ': 'UTC'},
            volumes=['postgres-data:/var/lib/postgresql/data'],
            tmpfs={**tmp, '/var/run/postgresql': 'rw,nosuid,size=16m,uid=999,gid=999'},
            healthcheck=health(['pg_isready', '-U', 'postgres', '-d', 'langfuse'])),
        'clickhouse': service('clickhouse-clickhouse-server', 1024, name='clickhouse', user='101:101',
            read_only=False,  # Upstream entrypoint writes its owned users.d config.
            environment={'CLICKHOUSE_DB': 'default', 'CLICKHOUSE_USER': 'clickhouse',
                         'CLICKHOUSE_PASSWORD': secrets['clickhouse']},
            volumes=['clickhouse-data:/var/lib/clickhouse', 'clickhouse-logs:/var/log/clickhouse-server'],
            tmpfs=tmp, ulimits={'nofile': {'soft': 262144, 'hard': 262144}},
            healthcheck=health(['wget', '--no-verbose', '--tries=1', '--spider', 'http://localhost:8123/ping'])),
        'redis': service('library-redis', 128, name='redis', cap_add=root_caps,
            environment={'REDISCLI_AUTH': secrets['redis']},
            command=['redis-server', '--requirepass', secrets['redis'], '--maxmemory', '96mb',
                     '--maxmemory-policy', 'noeviction'],
            volumes=volumes('redis-data'), tmpfs=tmp,
            healthcheck=health(['redis-cli', 'ping'])),
        'minio': service('chainguard-minio', 384, name='minio', user='65532:65532',
            command=['server', '--address', ':9000', '--console-address', ':9001', '/data'],
            environment={'MINIO_ROOT_USER': 'aeepminio', 'MINIO_ROOT_PASSWORD': secrets['minio']},
            volumes=volumes('minio-data'), tmpfs=tmp,
            healthcheck=health(['mc', '--config-dir', '/tmp/mc-ready', 'ready', 'local'])),
        'minio-bucket': service('chainguard-minio', 128, name='minio-bucket', user='501:20',
            entrypoint=['/usr/bin/mc'],
            command=['--config-dir', '/run/mc', 'mb', '--ignore-existing', 'aeep/langfuse'],
            volumes=[{'type': 'bind', 'source': str(work/'mc'), 'target': '/run/mc', 'read_only': False}],
            tmpfs=tmp),
        'web': service('langfuse-langfuse', 1024, name='web', user='1001:1001',
            command=['node', 'web/server.js', '--keepAliveTimeout', '110000'],
            environment={**environment, 'HOSTNAME': '0.0.0.0', 'PORT': '3000',
                'NEXTAUTH_SECRET': secrets['nextauth'],
                'LANGFUSE_INIT_ORG_ID': 'cm0000000000000000000aeep0',
                'LANGFUSE_INIT_ORG_NAME': 'AEEP private engineering',
                'LANGFUSE_INIT_PROJECT_ID': 'cm0000000000000000000aeep1',
                'LANGFUSE_INIT_PROJECT_NAME': 'Receipt linkage engineering',
                'LANGFUSE_INIT_PROJECT_PUBLIC_KEY': 'pk-lf-'+secrets['public'],
                'LANGFUSE_INIT_PROJECT_SECRET_KEY': 'sk-lf-'+secrets['secret'],
                'LANGFUSE_INIT_USER_EMAIL': 'aeep-local@example.invalid',
                'LANGFUSE_INIT_USER_NAME': 'Local engineering operator',
                'LANGFUSE_INIT_USER_PASSWORD': secrets['password']},
            ports=[{'target': 3000, 'published': str(PORT), 'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
            tmpfs={**tmp, '/app/web/.next/cache': 'rw,noexec,nosuid,size=32m,uid=1001,gid=1001'}),
        'worker': service('langfuse-langfuse-worker', 1024, name='worker', user='1001:1001',
            environment=environment, tmpfs=tmp),
    }
    return {'name': PROJECT, 'services': services,
            'networks': {'private': {'name': PROJECT+'-private', 'internal': True,
                                    'labels': {LABEL: PROJECT}}},
            'volumes': {name: {'name': PROJECT+'-'+name, 'labels': {LABEL: PROJECT}}
                        for name in ('postgres-data', 'clickhouse-data', 'clickhouse-logs', 'minio-data', 'redis-data')}}


def mc_config(secrets):
    return {'version': '10', 'aliases': {'aeep': {'url': 'http://minio:9000',
            'accessKey': 'aeepminio', 'secretKey': secrets['minio'], 'api': 'S3v4', 'path': 'auto'}}}


def ingestion_match(body, expected):
    """Match exact upstream observation IDs and receipt hash; no fuzzy names."""
    if not isinstance(body, dict) or not isinstance(body.get('data'), list):
        return False
    def contains(value, digest):
        if isinstance(value, dict):return any(contains(v, digest) for v in value.values())
        if isinstance(value, list):return any(contains(v, digest) for v in value)
        return value == digest
    return any(isinstance(row, dict) and row.get('id') == expected['span_id']
        and row.get('traceId') == expected['trace_id']
        and contains(row.get('metadata'), expected['source_receipt_sha256']) for row in body['data'])
