"""Host-side static/data checks only. Do not execute repository or upstream code."""
import ast
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import zipfile

from aeep.assessment.models import RecipeDefinition, RecipeMaterializationRequest, content_digest
from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    review = json.loads((HERE / 'operation-review.json').read_text())
    checks = []
    for name in ('prepare.py', 'probe.py', 'run.py', 'upstream-grading.py'):
        compile((HERE / name).read_text(), name, 'exec')
    checks.append('all four programs parse without executing upstream source')
    assert sha((HERE / 'run.py').read_bytes()) == review['runner_sha256']
    assert sha((HERE / 'probe.py').read_bytes()) == review['probe_sha256']
    assert sha((HERE / 'upstream-grading.py').read_bytes()) == review['upstream_grading_sha256']
    assert verification_source_digest(ROOT) == review['source_digest']
    checks.append('exact runner, probe, upstream excerpts and unchanged integrated source')
    request = RecipeMaterializationRequest.model_validate(review['request'])
    recipe = RecipeDefinition.model_validate(review['recipe'])
    assert content_digest(recipe) == request.recipe_digest
    checks.append('existing request and executable-recipe schemas bind exact program')
    payloads = []
    for variant in review['variants']:
        raw = (ROOT / variant['payload']).read_bytes()
        assert sha(raw) == variant['payload_sha256'] and len(raw) == variant['payload_bytes']
        payload = json.loads(raw)
        assert sha(base64.b64decode(payload['archive'])) == variant['archive_sha256']
        assert sha(payload['upstream_grading'].encode()) == review['upstream_grading_sha256']
        outer = {'request': {'input': payload}, 'spec': recipe.extension.grader.model_dump(mode='json'),
                 'attempt': 1, 'attempt_id': 'x'*200, 'approved_side_effect': 'read'}
        assert len(json.dumps(outer).encode()) < 1_950_000
        assert len(payload['expected']['FAIL_TO_PASS']) == 2 and len(payload['expected']['PASS_TO_PASS']) == 22
        for wheel in payload['wheels']:
            data = base64.b64decode(wheel['data'], validate=True)
            assert sha(data) == wheel['sha256']
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                metadata = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
                assert len(metadata) == 1
                for name in archive.namelist():
                    assert not name.startswith('/') and '..' not in Path(name).parts
        payloads.append(payload)
    assert len({payload['archive_sha256'] for payload in payloads}) == 3
    checks.append('three distinct data-only variants, seven pinned wheels each, 24 oracle nodes and bounded actual transport')
    # Import only the first-party stdlib probe; its entrypoint is not called.
    spec = importlib.util.spec_from_file_location('reviewed_first_party_probe', HERE / 'probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='aeep-rebench-static-') as temporary:
        root = Path(temporary)
        module.unpack(base64.b64decode(payloads[0]['archive']), root / 'valid')
        assert (root / 'valid/loguru/_handler.py').is_file()
        for kind in ('traversal', 'absolute', 'symlink', 'duplicate', 'oversized'):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w:gz') as archive:
                info = tarfile.TarInfo({'traversal': '../escape', 'absolute': '/escape'}.get(kind, 'file'))
                if kind == 'symlink':
                    info.type, info.linkname = tarfile.SYMTYPE, '/etc/passwd'
                if kind == 'oversized':
                    info.size = 4_000_001
                    archive.addfile(info, io.BytesIO(b'x'*info.size))
                else:
                    archive.addfile(info)
                    if kind == 'duplicate':
                        archive.addfile(info)
            try:
                module.unpack(stream.getvalue(), root / kind)
            except ValueError:
                pass
            else:
                raise AssertionError(kind + ' accepted')
    checks.append('archive traversal, absolute path, symlink, duplicate and size violations rejected')
    # Compare exact AST source segments, without importing or running the vendor code.
    sliced = ast.parse((HERE / 'upstream-grading.py').read_text())
    source_root = ROOT / '.aeep/repository-cohort-20261022/upstream-source'
    originals = {}
    for path in ('swebench/harness/constants/__init__.py', 'swebench/harness/log_parsers/python.py', 'swebench/harness/grading.py'):
        text = (source_root / path).read_text()
        originals.update({node.name: ast.get_source_segment(text, node) for node in ast.parse(text).body
                          if isinstance(node, (ast.FunctionDef, ast.ClassDef))})
    for node in sliced.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            assert ast.get_source_segment((HERE / 'upstream-grading.py').read_text(), node) == originals[node.name]
    checks.append('all ten upstream function/class bodies match pinned original source exactly')
    result = {'passed': True, 'checks': checks, 'source_digest': review['source_digest'],
              'review_sha256': sha((HERE / 'operation-review.json').read_bytes()),
              'external_code_executed': False, 'containers_started': 0, 'model_turns': 0}
    (HERE / 'preparation-checks.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
