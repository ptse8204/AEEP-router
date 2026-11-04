"""Read only public OCI manifests/configs; no layers or private credentials."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAXIMUM = 512 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def get(url, headers=None):
    for _ in range(4):
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with opener.open(request, timeout=20) as response:
                raw = response.read(MAXIMUM + 1)
                assert len(raw) <= MAXIMUM
                return raw
        except urllib.error.HTTPError as error:
            if error.code not in {301, 302, 303, 307, 308}:
                raise
            next_url = error.headers['Location']
            parsed = urllib.parse.urlsplit(next_url)
            assert parsed.scheme == 'https' and not parsed.username and not parsed.password
            assert parsed.hostname in {
                'production.cloudflare.docker.com', 'production.cloudfront.docker.com',
                'docker.langfuse.com', 'registry-1.docker.io',
            } or (parsed.hostname or '').endswith('.r2.cloudflarestorage.com')
            url, headers = next_url, {}  # Never forward the public token across origins.
    raise ValueError('metadata redirect ceiling')


def main():
    selected = json.loads((HERE / 'selected-source-authenticated-metadata.json').read_bytes())
    record = {'evidence_kind': 'public OCI metadata only',
              'observed_at': datetime.now(UTC).isoformat(),
              'selected_source_revision': selected['selected_source_revision'],
              'images': [], 'services_started': 0, 'image_layers_downloaded': 0}
    for index in selected['observations']:
        if index.get('status') != 200:
            continue
        repo = index['repository']
        row = {'repository': repo, 'tag': '4.55.0', 'index_digest': index['digest']}
        try:
            token_url = 'https://auth.docker.io/token?' + urllib.parse.urlencode({
                'service': 'registry.docker.io', 'scope': 'repository:' + repo + ':pull'})
            token = json.loads(get(token_url))['token']
            headers = {'Authorization': 'Bearer ' + token,
                       'Accept': 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'}
            digest = index['arm64'][0]['digest']
            raw = get('https://docker.langfuse.com/v2/' + repo + '/manifests/' + digest, headers)
            assert 'sha256:' + hashlib.sha256(raw).hexdigest() == digest
            manifest = json.loads(raw)
            stem = repo.replace('/', '-') + '-4.55.0-arm64'
            (HERE / (stem + '-manifest.json')).write_bytes(raw)
            config_raw = get('https://docker.langfuse.com/v2/' + repo + '/blobs/' + manifest['config']['digest'], headers)
            token = None
            assert 'sha256:' + hashlib.sha256(config_raw).hexdigest() == manifest['config']['digest']
            config = json.loads(config_raw)
            (HERE / (stem + '-config.json')).write_bytes(config_raw)
            row.update(linux_arm64_manifest_digest=digest,
                       config_digest=manifest['config']['digest'], architecture=config['architecture'],
                       os=config['os'], compressed_layer_bytes=sum(layer['size'] for layer in manifest['layers']),
                       labels=config.get('config', {}).get('Labels', {}), status='METADATA_VERIFIED')
            row['source_revision_matches_selected'] = row['labels'].get('org.opencontainers.image.revision') == selected['selected_source_revision']
        except urllib.error.HTTPError as error:
            row.update(status='METADATA_FAILED', error_type='HTTPError', http_status=error.code)
        except Exception as error:
            row.update(status='METADATA_FAILED', error_type=type(error).__name__)
        record['images'].append(row)
        (HERE / 'selected-source-image-configs.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
