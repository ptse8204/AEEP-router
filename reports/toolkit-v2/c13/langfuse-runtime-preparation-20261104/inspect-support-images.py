"""Inspect existing dependency pins; never fetch an image layer or run Docker."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.error
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('public_oci_metadata', HERE / 'inspect-images.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

# Anonymous public config blobs may redirect here. Strip Authorization on every redirect.
old = helper.get


def get(url, headers=None):
    for _ in range(4):
        try:
            request = helper.urllib.request.Request(url, headers=headers or {})
            with helper.opener.open(request, timeout=20) as response:
                raw = response.read(helper.MAXIMUM + 1)
                assert len(raw) <= helper.MAXIMUM
                return raw
        except urllib.error.HTTPError as error:
            if error.code not in {301, 302, 303, 307, 308}:
                raise
            url = error.headers['Location']
            parsed = urllib.parse.urlsplit(url)
            assert parsed.scheme == 'https' and not parsed.username and not parsed.password
            assert parsed.hostname in {
                'production.cloudflare.docker.com', 'production.cloudfront.docker.com',
                'cgr.dev', 'storage.googleapis.com',
            } or (parsed.hostname or '').endswith('.r2.cloudflarestorage.com')
            headers = {}
    raise ValueError('public metadata redirect ceiling')


def main():
    previous = json.loads((HERE.parent / 'full-stack-20261030/langfuse-image-metadata.json').read_bytes())
    record = {'observed_at': datetime.now(UTC).isoformat(),
              'scope': 'original pinned supporting image metadata, no execution',
              'images': [], 'image_layers_downloaded': 0, 'services_started': 0}
    for source in previous['images']:
        registry, repo = source['registry'], source['repository']
        if registry == 'docker.langfuse.com':
            continue
        row = {'registry': registry, 'repository': repo,
               'linux_arm64_manifest_digest': source['linux_arm64_manifest_digest'],
               'previous_tag': source['requested_tag']}
        try:
            token_url = ('https://auth.docker.io/token?' if registry == 'registry-1.docker.io'
                         else 'https://cgr.dev/token?') + urllib.parse.urlencode({
                             'service': 'registry.docker.io' if registry == 'registry-1.docker.io' else 'cgr.dev',
                             'scope': 'repository:' + repo + ':pull'})
            token = json.loads(get(token_url)).get('token')
            assert token
            headers = {'Authorization': 'Bearer ' + token,
                       'Accept': 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'}
            raw = get('https://' + registry + '/v2/' + repo + '/manifests/' + row['linux_arm64_manifest_digest'], headers)
            assert 'sha256:' + hashlib.sha256(raw).hexdigest() == row['linux_arm64_manifest_digest']
            manifest = json.loads(raw)
            stem = repo.replace('/', '-') + '-pinned-arm64'
            (HERE / (stem + '-manifest.json')).write_bytes(raw)
            # Deliberately fetch only the config descriptor, never manifest.layers.
            config_raw = get('https://' + registry + '/v2/' + repo + '/blobs/' + manifest['config']['digest'], headers)
            token = None
            assert 'sha256:' + hashlib.sha256(config_raw).hexdigest() == manifest['config']['digest']
            config = json.loads(config_raw)
            assert config['architecture'] == 'arm64' and config['os'] == 'linux'
            (HERE / (stem + '-config.json')).write_bytes(config_raw)
            row.update(status='METADATA_VERIFIED', config_digest=manifest['config']['digest'],
                       compressed_layer_bytes=sum(layer['size'] for layer in manifest['layers']),
                       labels=config.get('config', {}).get('Labels', {}),
                       user=config.get('config', {}).get('User'),
                       entrypoint=config.get('config', {}).get('Entrypoint'),
                       command=config.get('config', {}).get('Cmd'))
        except urllib.error.HTTPError as error:
            row.update(status='METADATA_FAILED', error_type='HTTPError', http_status=error.code)
        except Exception as error:
            row.update(status='METADATA_FAILED', error_type=type(error).__name__)
        record['images'].append(row)
        (HERE / 'support-image-configs.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({**record, 'images': [{k: v for k, v in row.items() if k not in {'labels', 'command', 'entrypoint'}} for row in record['images']]}, indent=2))


if __name__ == '__main__':
    main()
