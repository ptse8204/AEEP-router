"""Audit source/patch data with AST and git apply; never run repository code."""
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def body(data):
    tree = ast.parse(data)
    class StripDocumentation(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return None
            return self.generic_visit(node)
    tree = StripDocumentation().visit(tree)
    return ast.dump(tree, include_attributes=False)


def imports(data):
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError):
        return set()
    return {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names} | {(node.module or '').split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and not node.level}


def main():
    spec = importlib.util.spec_from_file_location('aeep_inert_patch_preparation', HERE.parent / 'repository-suite-integration-20261022/prepare-development-assets.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    records = json.loads((HERE / 'source-review.json').read_text())['sources']
    results = []
    for record in records:
        if record['status'] != 'STATIC_REVIEW_REQUIRED':
            continue
        directory = ROOT / record['private_cache']
        row = json.loads((directory / 'row.json').read_text())
        result = {'instance_id': row['instance_id'], 'repository': row['repo'], 'source_revision': row['base_commit'], 'private_cache': record['private_cache']}
        try:
            raw = (directory / 'source.tar.gz').read_bytes()
            assert sha(raw) == record['archive_sha256']
            files, normalized = helper.normalize(raw)
            with tempfile.TemporaryDirectory(prefix='aeep-inert-source-', dir='/private/tmp') as temporary:
                work = Path(temporary).resolve()
                for name, data in files.items():
                    path = work / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                helper.apply(work, row['test_patch'], work.parent)
                after_test = {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()}
                assert set(files) <= after_test.keys()
                test_changes = {n: data for n, data in after_test.items() if files.get(n) != data}
                helper.apply(work, row['patch'], work.parent)
                fixed = {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()}
                assert set(fixed) == set(after_test)
            changes = sorted(n for n in fixed if fixed[n] != after_test[n])
            source_changes = [n for n in changes if n.endswith('.py') and not set(PurePosixPath(n).parts) & {'test', 'tests', 'testing'} and n not in ('setup.py', 'conftest.py')]
            executable = [n for n in source_changes if body(after_test[n]) != body(fixed[n])]
            selected = sorted({n.split('::')[0] for n in row['FAIL_TO_PASS'] + row['PASS_TO_PASS']})
            test_data = {**files, **test_changes}
            assert all(n in test_data for n in selected)
            test_imports = set().union(*(imports(test_data[n]) for n in selected), *(imports(v) for n, v in test_data.items() if n.endswith('conftest.py')))
            package_roots = {PurePosixPath(n).parts[1] if n.startswith('src/') else PurePosixPath(n).parts[0] for n in source_changes}
            local = {PurePosixPath(n).parts[0].removesuffix('.py') for n in files} | {PurePosixPath(n).parts[1].removesuffix('.py') for n in files if n.startswith('src/')}
            package_imports = set().union(*(imports(v) for n, v in files.items() if n.endswith('.py') and ((n.split('/')[0] in package_roots) or (n.startswith('src/') and n.split('/')[1] in package_roots))))
            external = sorted((test_imports | package_imports) - sys.stdlib_module_names - local - {''})
            result.update(status='STATIC_AUDIT_COMPLETE', executable_source_files=executable,
                          changed_python_source_files=source_changes, omitted_non_source_candidates=[n for n in changes if n not in source_changes],
                          protected_overlay_paths=sorted(test_changes), overlay_outside_tests=[n for n in test_changes if not n.startswith('tests/')],
                          family='multi-file-repair' if len(executable) > 1 else 'single-file-repair' if len(executable) == 1 else 'EXCLUDE_NO_EXECUTABLE_CHANGE',
                          normalized_source_bytes=len(normalized), required_bug_tests=len(row['FAIL_TO_PASS']), preservation_tests=len(row['PASS_TO_PASS']),
                          selected_test_modules=selected, source_roots=sorted(package_roots), external_static_import_roots=external,
                          licenses=record['licenses'], problem_characters=len(row['problem_statement']) + len(row.get('interface') or ''),
                          dependency_note='Static imports include optional/TYPE_CHECKING branches and are incomplete for dynamic imports; not a verified runtime closure.')
        except Exception as exc:
            result.update(status='UNRESOLVED', error_type=type(exc).__name__, error=str(exc)[:200])
        results.append(result)
    output = {'sources': results, 'cases_adopted': 0, 'stages_frozen': False, 'external_code_executed': False,
              'family_review': 'AST bodies with docstrings removed reject file-count inflation; not proof of semantic difficulty or behavior coverage.'}
    (HERE / 'source-data-audit-v2.json').write_text(json.dumps(output, indent=2) + '\n')
    for item in results:
        print(item['instance_id'], item['status'], item.get('family'), item.get('executable_source_files'), item.get('external_static_import_roots', item.get('error')))


if __name__ == '__main__':
    main()
