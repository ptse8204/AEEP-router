"""Read public metadata for exact locked versions; no archive or code execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
LOCK = HERE.parent / 'skillrank-build-preparation-20261103/locked-crates.json'
lock = json.loads(LOCK.read_bytes())


def inspect(item):
    url = 'https://crates.io/api/v1/crates/' + item['name'] + '/' + item['version']
    request = urllib.request.Request(url, headers={'User-Agent': 'AEEP-read-only-pinned-license-audit/1'})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=20) as stream:
            raw = stream.read(262145)
            if len(raw) > 262144 or stream.geturl() != url:
                raise ValueError('Metadata response too large or redirected')
        metadata = json.loads(raw)['version']
        if (metadata['num'] != item['version'] or metadata['crate'] != item['name']
                or metadata['checksum'] != item['sha256']):
            raise ValueError('Metadata version/checksum differs from pinned Cargo.lock')
        return {'name': item['name'], 'version': item['version'], 'archive_sha256': item['sha256'],
                'metadata_url': url, 'response_sha256': hashlib.sha256(raw).hexdigest(),
                'license_expression': metadata.get('license'), 'rust_version': metadata.get('rust_version'),
                'compressed_bytes_claim': metadata.get('crate_size'), 'passed': True}
    except Exception as error:
        return {'name': item['name'], 'version': item['version'], 'metadata_url': url,
                'passed': False, 'error_type': type(error).__name__}


with ThreadPoolExecutor(max_workers=4) as pool:
    rows = list(pool.map(inspect, lock['files']))
payload = {'observed_at': datetime.now(UTC).isoformat(), 'passed': all(r['passed'] for r in rows),
           'source_lock_sha256': lock['Cargo_lock_sha256'], 'rows': rows,
           'scope': 'Mutable registry metadata bound to exact version/archive checksum; actual archive manifests must still match before compilation.',
           'archive_downloads': 0, 'upstream_executed': False, 'models': 0}
(HERE / 'registry-metadata-audit.json').write_text(json.dumps(payload, indent=2) + '\n')
print(json.dumps({'passed': payload['passed'], 'versions': len(rows),
                  'failed': [r['name'] for r in rows if not r['passed']],
                  'license_expressions': sorted({r['license_expression'] for r in rows if r['passed']}),
                  'archive_downloads': 0, 'upstream_executed': False}))
