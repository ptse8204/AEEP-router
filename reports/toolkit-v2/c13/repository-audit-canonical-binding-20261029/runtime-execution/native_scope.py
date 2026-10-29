"""Reviewed operator data derivation; no subject imports or execution."""
import ast
import copy
import hashlib
import json
from pathlib import Path

from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAssetV5, archive_files, pack_files


def expand(fail_to_pass, pass_to_pass, native_ids, test_paths):
    aliases = fail_to_pass + pass_to_pass
    if not isinstance(native_ids, list) or any(not isinstance(n, str) for n in [*aliases, *native_ids]):
        raise ValueError('Native identities must be strings')
    if not aliases or len(set(aliases)) != len(aliases) or not native_ids or len(native_ids) > 10000 or len(set(native_ids)) != len(native_ids):
        raise ValueError('Required aliases and collected identities must be distinct and bounded')
    if any(not n.strip() or not n.isprintable() or len(n.encode('utf-8')) > 8192 for n in [*aliases, *native_ids]):
        raise ValueError('Invalid native identity')
    groups, covered = {}, set()
    for alias in aliases:
        parameterized = '[' in alias.rsplit('::', 1)[-1]
        matches = sorted(n for n in native_ids if n == alias or parameterized and n.split()[0] == alias)
        if not matches or set(matches) & covered:
            raise ValueError('Missing or overlapping alias group')
        if any(n.split('::')[0] not in test_paths or '::' not in n for n in matches):
            raise ValueError('Native identity outside frozen test modules')
        groups[alias] = matches
        covered.update(matches)
    expanded = [n for alias in aliases for n in groups[alias]]
    if len(expanded) > 5000 or len(json.dumps(expanded)) > 300000:
        raise ValueError('Expanded obligation bound exceeded')
    f2p = [n for alias in fail_to_pass for n in groups[alias]]
    p2p = [n for alias in pass_to_pass for n in groups[alias]]
    assert not set(f2p) & set(p2p) and len(expanded) >= len(aliases)
    return f2p, p2p, groups


def derive(seed, collection, target):
    """Freeze a new authored scope before grading; only one selector literal changes."""
    if collection['exit_code'] != 0 or collection['python'] != seed.truth.python or collection['pytest'] != seed.truth.pytest:
        raise ValueError('Native collection did not complete on the reviewed runtime')
    f2p, p2p, groups = expand(seed.truth.fail_to_pass, seed.truth.pass_to_pass, collection['native_ids'], seed.truth.test_paths)
    overlay = archive_files(seed.truth.tests.read(), large=True)
    paths = [n for n, data in overlay.items() if b'_AEEP_REQUIRED_NODES =' in data]
    if len(paths) != 1:
        raise ValueError('Exactly one first-party selector is required')
    path = paths[0]
    original = overlay[path].decode()
    tree = ast.parse(original)
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_AEEP_REQUIRED_NODES' for t in n.targets))
    aliases = seed.truth.fail_to_pass + seed.truth.pass_to_pass
    if (not isinstance(assignment.value, ast.Call) or ast.literal_eval(assignment.value.args[0]) != aliases
            or assignment.lineno != assignment.end_lineno):
        raise ValueError('Seed selector does not match the frozen alias list')
    lines = original.splitlines(keepends=True)
    lines[assignment.lineno - 1] = '_AEEP_REQUIRED_NODES = frozenset(' + repr(f2p + p2p) + ')\n'
    changed = ''.join(lines)
    # Independently prove all remaining AST nodes,including assertions/hooks,identical.
    after = ast.parse(changed)
    other = next(n for n in after.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_AEEP_REQUIRED_NODES' for t in n.targets))
    for node in (assignment, other):
        node.value = ast.Constant(value='selector data removed for comparison')
    assert ast.dump(tree, include_attributes=False) == ast.dump(after, include_attributes=False)
    overlay[path] = changed.encode()
    data = pack_files(overlay, large=True)
    target = Path(target)
    with target.open('xb') as stream:
        stream.write(data)
    value = seed.model_dump(mode='json')
    value['truth'].update(tests=SuiteAssetV5(path=str(target.resolve()), sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data)).model_dump(mode='json'), fail_to_pass=f2p, pass_to_pass=p2p)
    value['provenance'] += ' Exhaustive source-bound native alias expansion frozen before body trials;every matched identity is required. Original aliases and collection are retained;not an official benchmark score.'
    result = RepositorySuiteCase.model_validate(value)
    assert result.input == seed.input and result.reference == seed.reference and result.fault_outputs == seed.fault_outputs
    assert result.truth.source == seed.truth.source and result.truth.wheels == seed.truth.wheels
    unchanged = copy.deepcopy(seed.truth.model_dump(mode='json'))
    for key in ('tests', 'fail_to_pass', 'pass_to_pass'):
        unchanged[key] = result.truth.model_dump(mode='json')[key]
    assert unchanged == result.truth.model_dump(mode='json')
    return result, {'original_required_aliases': len(aliases), 'expanded_required_identities': len(f2p + p2p),
        'alias_groups': groups, 'selector_path': path, 'only_selector_literal_changed': True,
        'source_assertions_and_repairs_unchanged': True, 'collection_is_not_grade': True,
        'frozen_before_body_trials': True, 'derived_tests_sha256': result.truth.tests.sha256}
