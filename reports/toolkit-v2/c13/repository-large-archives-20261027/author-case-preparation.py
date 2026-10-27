"""Reuse the existing inert curator with explicit larger-profile data bounds."""
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-test-roots-20261027'
s=(OLD/'prepare-rooted-cases.py').read_text()
s=s.replace('import hashlib','import hashlib\nimport gzip\nimport io\nimport tarfile',1)
s=s.replace('SuiteTruthV4, archive_files','SuiteTruthV5, SuiteAssetV5, archive_files')
s=s.replace("ROOT / '.aeep/repository-test-root-cases-20261027'","ROOT / '.aeep/repository-large-cases-20261027'")
a=s.index('ENTRIES = [');b=s.index('\n\n\n',a);s=s[:a]+s[b:]
s=s.replace('def asset(path):\n    return SuiteAsset(',"def asset(path, *, large=False):\n    kind = SuiteAssetV5 if large else SuiteAsset\n    return kind(")
s=s.replace("    source_records = {x['instance_id']: x for x in json.loads((HERE / 'source-review.json').read_text())['sources']}","    source_records = {x['instance_id']: x for x in json.loads((HERE / 'source-size-review.json').read_text())['sources'] if x['status'] == 'STATIC_REVIEW_REQUIRED'}\n    entries = [(identity, record['proposed_audit'], []) for identity, record in source_records.items() if record['repository'] != 'agronholm/anyio']")
a=s.index('    scopes = {');b=s.index('\n',a);s=s[:a]+"    scopes = {}"+s[b:]
s=s.replace("HERE / 'pure-wheel-review.json'","HERE.parent / 'repository-test-roots-20261027/pure-wheel-review.json'")
s=s.replace('in ENTRIES:','in entries:')
s=s.replace('files, _ = helper.normalize(raw)','files = normalize_large(raw)')
s=s.replace('source = pack_files(public)','source = pack_files(public, large=True)')
s=s.replace('tests.write_bytes(pack_files(overlay))','tests.write_bytes(pack_files(overlay, large=True))')
s=s.replace('source=asset(src), tests=asset(tests)','source=asset(src, large=True), tests=asset(tests, large=True)')
s=s.replace("truth = SuiteTruthV4(**kwargs,", "truth = SuiteTruthV5(**kwargs, archive_profile='repository-v1',")
s=s.replace("schema_version='assessment.repository-suite-case.v4'","schema_version='assessment.repository-suite-case.v5'")
s=s.replace("            omitted_scope_docs = []","            omitted_scope_docs = []")
normalize='''
def normalize_large(data):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
        raw=compressed.read(24_000_001)
    assert len(raw)<=24_000_000
    files={};prefix=None
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for item in archive:
            parts=Path(item.name).parts
            assert parts and not Path(item.name).is_absolute() and '..' not in parts
            prefix=prefix or parts[0];assert prefix==parts[0]
            if item.isdir():continue
            assert item.isfile()
            name='/'.join(parts[1:]);assert name not in files
            files[name]=archive.extractfile(item).read()
    encoded=pack_files(files,large=True)
    assert archive_files(encoded,large=True)==files
    return files

'''
s=s.replace('async def main():',normalize+'\nasync def main():')
# Only the protected overlay and current public archive use larger assets. The
# patch/wheel bounds and all reference/assertion guards stay unchanged.
(HERE/'prepare-cases.py').write_text(s)
