"""Read bounded, pinned source archives as inert data. Never import subject code."""
import ast
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CACHE = ROOT / '.aeep/repository-workload-batch-20261022-sources'
BOUND = 650_000
REPOSITORIES = ()
EXPLICIT_SQLGLOT = {'tox-dev__tox-3846', 'yukinarit__pyserde-682', 'reagento__dishka-512', 'lincolnloop__goodconf-51', 'modelcontextprotocol__python-sdk-384', 'psf__black-4952', 'copier-org__copier-2646', 'microsoft__fabric-cicd-465', 'stuartmaxwell__djpress-117', 'noppanut15__depthviz-55', 'vitalik__django-ninja-1427', 'psf__black-4676', 'elementsinteractive__twyn-317', 'tox-dev__tox-3683', 'microsoft__fabric-cicd-670', 'a2aproject__a2a-python-576', 'ethereum__eth-account-317', 'noppanut15__depthviz-56', 'agronholm__anyio-975', 'ua-parser__uap-python-255', 'lmstudio-ai__venvstacks-197', 'microsoft__fabric-cicd-394', 'modelcontextprotocol__python-sdk-1864', 'pycqa__isort-2491', 'wireservice__csvkit-1274', 'intel__code-base-investigator-178', 'bodo-ai__PyDough-368', 'sphinx-doc__sphinx-13318', 'agronholm__anyio-1134', 'agronholm__anyio-1121', 'tox-dev__tox-3759', 'MAIF__arta-50', 'tox-dev__tox-3810', 'yukinarit__pyserde-657', 'a2aproject__a2a-python-472', 'sphinx-doc__sphinx-13261', 'googlefonts__glyphsLib-1060', 'wemake-services__wemake-python-styleguide-3382', 'agronholm__anyio-935', 'joshuadavidthomas__django-bird-239', 'marcosschroh__dataclasses-avroschema-870', 'modelcontextprotocol__python-sdk-222', 'scientific-python__docstub-123', 'asottile__dead-204', 'boxed__mutmut-403', 'a2aproject__a2a-python-682_interface', 'tox-dev__tox-3931', 'sphinx-doc__sphinx-13382', 'marcosschroh__dataclasses-avroschema-835', 'py-pdf__pdfly-219'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 100 * 1024**2
    CACHE.mkdir(exist_ok=False)
    meta = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json').read_text())
    inv = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-suite-integration-20261022/cohort-inventory.json').read_text())
    eligible = {x['instance_id']: x for x in inv['rows'] if not x['metadata_blockers']}
    selected = {}
    for source in meta['sources']:
        path = ROOT / source['private_cache']
        assert sha(path.read_bytes()) == source['sha256']
        for item in json.loads(path.read_text())['rows']:
            row = item['row']
            if row['repo'] not in REPOSITORIES and row['instance_id'] not in EXPLICIT_SQLGLOT:
                continue
            if row['instance_id'] in eligible and all(n.startswith('tests/') for n in row['FAIL_TO_PASS'] + row['PASS_TO_PASS']):
                selected[row['instance_id']] = row
    rows = [selected[k] for k in sorted(selected)]
    assert len(rows) <= 50
    screening = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-declared-tests-20261022/composed-screening-reproduction.json').read_text())
    excluded = {x['repository'].removeprefix('https://github.com/').casefold() for x in screening['cases']} | {'delgan/loguru', 'pallets/click', 'marshmallow-code/marshmallow', 'pgmpy/pgmpy'}
    assert not {x['repo'].casefold() for x in rows} & excluded
    (CACHE / 'queue.json').write_text(json.dumps(rows, indent=2) + '\n')
    queue = {'selection_basis': 'Pinned public metadata only; bounded static source/license/runtime triage, no outcome-based stage assignment.',
             'dataset_revision': meta['revision_before_and_after'], 'rows': len(rows), 'repositories': len({x['repo'] for x in rows}),
             'compressed_bytes_per_read': BOUND + 1, 'maximum_download_bytes': len(rows) * (BOUND + 1),
             'excluded_development_and_screening_repositories': sorted(excluded),
             'identities': [x['instance_id'] for x in rows], 'cases_adopted': 0, 'stage_frozen': False}
    (HERE / 'source-queue.json').write_text(json.dumps(queue, indent=2) + '\n')

    def collect(row):
        repo, revision, identity = row['repo'], row['base_commit'], row['instance_id']
        assert re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) and re.fullmatch(r'[a-f0-9]{40}', revision)
        directory = CACHE / identity
        directory.mkdir()
        (directory / 'row.json').write_text(json.dumps(row, indent=2) + '\n')
        url = 'https://codeload.github.com/' + repo + '/tar.gz/' + revision
        record = {'instance_id': identity, 'repository': repo, 'revision': revision, 'url': url,
                  'private_cache': str(directory.relative_to(ROOT)), 'metadata_family_hint': eligible[identity]['family_hint'],
                  'declared_python': row['install_config']['python'], 'code_executed': False, 'stage': None}
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(urllib.request.Request(url, headers={'User-Agent': 'AEEP-source-review/2'}), timeout=25) as response:
                assert urllib.parse.urlparse(response.geturl()).hostname == 'codeload.github.com'
                data = response.read(BOUND + 1)
            (directory / 'source.tar.gz').write_bytes(data)
            record.update(downloaded_bytes=len(data), archive_sha256=sha(data))
            if len(data) > BOUND:
                record.update(status='NEEDS_SOURCE_SCOPE_REVIEW', reason='Whole archive exceeds transport bound; partial bytes retained, not parsed. No bound change authorized.')
                return record
            files, total, prefix, violations = {}, 0, None, []
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                for member in archive:
                    name = PurePosixPath(member.name)
                    assert not name.is_absolute() and '..' not in name.parts
                    prefix = prefix or name.parts[0]
                    assert prefix == name.parts[0]
                    if member.isdir():
                        continue
                    if not member.isfile():
                        violations.append('nonregular member')
                        continue
                    total += member.size
                    if total > 4_000_000 or len(files) >= 1000:
                        violations.append('unpacked bound')
                        break
                    relative = PurePosixPath(*name.parts[1:]).as_posix()
                    assert relative not in files
                    if set(PurePosixPath(relative).parts) & {'.git', '.codex', '.agents', 'AGENTS.md', 'auth.json'}:
                        violations.append('protected instruction/configuration path')
                    files[relative] = archive.extractfile(member).read()
            licenses, configs, imports = [], [], set()
            for name, content in files.items():
                if len(PurePosixPath(name).parts) == 1 and name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                    (directory / name).write_bytes(content)
                    licenses.append({'file': name, 'sha256': sha(content), 'bytes': len(content)})
                if name in ('pyproject.toml', 'setup.cfg', 'setup.py', 'requirements.txt', 'requirements-dev.txt', 'conftest.py', 'tests/conftest.py'):
                    target = directory / 'review-files' / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    configs.append({'file': name, 'sha256': sha(content), 'bytes': len(content)})
                if name.endswith('.py'):
                    try:
                        tree = ast.parse(content)
                        imports.update((n.module or '').split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and not n.level)
                        imports.update(a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names)
                    except (SyntaxError, ValueError):
                        pass
            record.update(status='STATIC_REVIEW_REQUIRED' if not violations else 'EXCLUDED',
                          reason='; '.join(sorted(set(violations))) if violations else 'License, executable change family, dependency and reproducibility review required.',
                          regular_files=len(files), unpacked_bytes=total, licenses=licenses, config_files=configs,
                          static_import_roots=sorted(imports - {''}))
        except Exception as exc:
            record.update(status='UNRESOLVED', error_type=type(exc).__name__, error=str(exc)[:180])
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(collect, rows))
    report = {**queue, 'sources': results, 'downloaded_bytes': sum(x.get('downloaded_bytes', 0) for x in results),
              'external_code_executed': False, 'installers': 0, 'models': 0, 'tests': 0}
    (HERE / 'source-review.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'rows': len(results), 'bytes': report['downloaded_bytes'],
                      'statuses': {status: sum(x['status'] == status for x in results) for status in sorted({x['status'] for x in results})}}))


if __name__ == '__main__':
    main()
