"""Freeze a concrete grouped review after source/package preparation; never execute."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, digest, snapshot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


source = verification_source_digest(ROOT)
checks_path = HERE.parent / 'report-family-serialization-20261103/verification/checks.json'
checks = load(checks_path)
assert checks['source_before'] == checks['source_after'] == source
assert len(checks['checks']) == 13 and all(c['exit_code'] == 0 for c in checks['checks'])
assert not (HERE / 'operation-review.json').exists()
assert shutil.disk_usage(ROOT).free >= 58 * 1024**3
package = load(HERE / 'package-preparation.json')
assert package['source'] == source and package['unchanged_dependencies'] == 32
plan = RuntimeInstallation.model_validate(load(HERE / 'package-installation.json'))
assert digest(plan) == package['installation_digest']
previous = load(HERE.parent / 'integration-snapshot-correction-20261103/operation-review.json')
docs = previous['docs']
docs['permitted_correction'] = 'Up to two offline attempts with these exact inputs/tools/config; stop after success. No source/tool repair or repeated successful check.'
from aeep.assessment.models import content_digest

document_hashes = {name: sha(ROOT / name) for name in docs['documents']}
docs_snapshot = ROOT / ('.aeep/skillrank-build-preparation-20261103/docs-inputs-' + content_digest(document_hashes)[:12])
docs_snapshot.mkdir(mode=0o700, exist_ok=True)
for name in docs['documents']:
    target = docs_snapshot / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == (ROOT / name).read_bytes()
    else:
        shutil.copyfile(ROOT / name, target)
assets = {}
for p in HERE.iterdir():
    if p.is_file() and p.suffix in {'.py', '.json', '.md', '.rs', '.sb'}:
        assets[str(p)] = sha(p)
for name in docs['documents']:
    assets[str(ROOT / name)] = sha(ROOT / name)
for name in ('Makefile', '.markdownlint-cli2.jsonc', '.lychee.toml'):
    assets[str(ROOT / name)] = sha(ROOT / name)
for name in ('/usr/local/bin/docker', sys.executable):
    assets[str(Path(name).resolve(strict=True))] = sha(name)
assets[str(checks_path)] = sha(checks_path)
image = load(HERE / 'compiler-image-metadata.json')['images'][0]
assert image['architecture'] == 'arm64' and image['os'] == 'linux'
context = ROOT / '.aeep/skillrank-build-preparation-20261103/context'
context_files = {p.relative_to(context).as_posix(): sha(p) for p in sorted(context.rglob('*')) if p.is_file()}
runtime = ROOT / '.aeep/skillrank-build-preparation-20261103/runtime'
assert not runtime.exists()
review = {
    'purpose': 'Build the selected SkillRank source and verify its actual local search/show; independently check corrected report wheel and offline docs. No comparative campaign.',
    'source': source, 'source_checks': str(checks_path), 'assets': assets,
    'executable_links': {name: str(Path(name).resolve(strict=True)) for name in ('/usr/local/bin/docker', sys.executable)},
    'expires_at': '2026-11-06T12:00:00Z',
    'runtime': str(runtime), 'build_context': str(context),
    'build_context_sha256': content_digest(context_files),
    'source_revision': '5216bae9149b4ff8a7f9e014b6889fb094cee8e1',
    'compiler_image': 'rust@' + image['digest'],
    'compiler_label': '1.94.1-slim-bookworm', 'compiler_architecture': 'linux/arm64',
    'compiler_image_compressed_bytes': image['size'],
    'compiler_pull': 'One exact anonymous DockerHub pull; normal public registry authentication and OCI blob delivery only. Reject configured mirrors; use an empty owned Docker client configuration, never host credentials.',
    'crate_sources': {'count': 86, 'lock': str(HERE / 'locked-crates.json'),
        'exact_public_origin': 'https://static.crates.io', 'maximum_http_attempts_each': 2,
        'redirects': False, 'maximum_compressed_bytes': 64 * 1024**2,
        'maximum_expanded_bytes': 512 * 1024**2,
        'license_guard': 'Record package SPDX expressions/license paths; stop before compilation on an expression outside the reviewed permissive/copyleft-source list in vendor.py. Private use only; no redistribution clearance is claimed.'},
    'runtime_execution': {'isolated_engineering_operations': 40, 'maximum_reserved_seconds': 4500,
        'maximum_model_turns': 0, 'cash_authority_usd': '0',
        'actual_cash_measurement': 'UNKNOWN', 'maximum_builds': 1, 'maximum_new_containers': 3,
        'maximum_search_readiness_attempts': 5,
        'boundary': 'Network none, read-only root/source/vendor/checks/catalog, only owned work writable, uid65534, no capabilities, no-new-privileges, 256 PIDs, 2CPU/2GiB memory/no swap. No host ports or credential/socket mounts.',
        'service': 'Actual upstream serve on container loopback18899; actual upstream search/show, missing-record failure and compiled first-party denial probe. Stop/remove only newly owned containers after checking exact IDs/image/label. Retain image, binary, context, vendor and logs.',
        'recorded_scope': 'Component build/search/show. Neither bounded evaluation nor full SkillRank integration is passed by this check.'},
    'storage': {'minimum_free_bytes': 50 * 1024**3, 'runtime_start_headroom_bytes': 8 * 1024**3,
        'runtime_net_capacity_stop_bytes': 6 * 1024**3,
        'preserve': 'All pre-existing images/containers/volumes/cache, runtimes, historical evidence, user work and backups. No pruning, image removal or old-resource cleanup.'},
    'package': {**package, 'runtime': plan.destination,
        'prepared_workspace_sha256': snapshot(HERE / 'package-execution/work'),
        'checks': 'Owned installer idempotency, denied home/outside writes/network, installed source hash, ordinary CLI help, v1/v2 schemas and repository-URL family normalization. Retain unchanged installed runtime.'},
    'docs': docs, 'checked_document_snapshot': str(docs_snapshot),
    'retained_resources': 'Compiler image and built runtime, current package runtime and existing offline checker remain. Only newly owned runtime-check containers are stopped/removed.',
    'accounting': 'Fresh finite zero-model component scope on the existing AssessmentRepository/ReceiptStore/CommandExecutor. Existing assessment grants/counters are neither changed nor reset. Retain partial operations/receipts. Client resource use is separate from container measurements; missing telemetry remains unknown.',
    'independence': 'Separate component attempt markers. A known settled component failure leaves other components eligible; unresolved source/authority/accounting/cleanup blocks dispatch. No automatic software/source replacement or repeated started trial.',
    'allowed_disclosure': 'Only public pinned Cargo/OCI artifact fetches. No model disclosure, prompts, task outputs, credentials or new model destinations.',
    'not_authorized': ['Models or comparative trials', 'Host/project/global installation or activation',
        'Additional dependencies, OS package installation, source-pin changes or automatic fallback',
        'Credential reading/copying, login, paid calls, payment, publication or release',
        'Image/volume/backups/old-runtime deletion', 'Changing the 50GiB reserve'],
    'approval_reason': 'The completed319d18e4 review allowed no downloads, builds or new dependencies and binds the older wheel. The continuation policy reserves untrusted installation/execution and container provisioning; this grouped review binds the new exact source/dependency/runtime artifacts. No architecture decision is requested.',
    'all_stack_complete': False, 'candidate_usefulness': 'NOT_ASSESSED',
    'selection_usefulness': 'NOT_ASSESSED', 'comparisons': 'PAUSED',
}
(HERE / 'operation-review.json').write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps({'review_sha256': sha(HERE / 'operation-review.json'), 'assets': len(assets),
                  'compiler_compressed_bytes': image['size'], 'models': 0, 'executed': False}))
