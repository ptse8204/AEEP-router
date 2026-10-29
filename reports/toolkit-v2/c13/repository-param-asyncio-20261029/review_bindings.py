"""Check each execution review's bindings before combining them; never shadow pins."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(paths, root):
    errors, checked, claims = [], {}, {}

    def binding(name, expected, where):
        path = Path(name)
        path = path if path.is_absolute() else root / path
        key = str(path.absolute())
        previous = claims.get(key)
        if previous and previous[0] != expected:
            errors.append({'kind': 'conflicting_pin', 'path': key,
                           'origins': [previous[1], where]})
        claims[key] = (expected, where)
        actual = sha(path) if path.is_file() and not path.is_symlink() else None
        if actual != expected:
            errors.append({'kind': 'file_binding', 'path': key, 'origin': where,
                           'expected': expected, 'actual': actual})

    def embedded(value, where):
        if isinstance(value, list):
            for index, item in enumerate(value):
                embedded(item, f'{where}[{index}]')
        elif isinstance(value, dict):
            for name, item in value.items():
                if name in ('assets', 'dependency_digests', 'runtime_dependencies'):
                    assert isinstance(item, dict), where
                    for path, expected in item.items():
                        binding(path, expected, f'{where}.{name}')
                else:
                    embedded(item, f'{where}.{name}')

    def review(path):
        path = Path(path).absolute()
        if str(path) in checked:
            return
        checked[str(path)] = sha(path)
        value = json.loads(path.read_text())
        embedded(value, str(path))
        for item in value.get('components', {}).values():
            target = Path(item['directory']) / item['review_file']
            binding(str(target), item['review_sha256'], str(path) + '.component')
            review(target)
        if 'template_review_sha256' in value:
            target = path.parent / 'template-operation-review.json'
            binding(str(target), value['template_review_sha256'], str(path) + '.template')
            review(target)
        if 'parent_review' in value and 'parent_review_sha256' in value:
            target = root / value['parent_review']
            binding(str(target), value['parent_review_sha256'], str(path) + '.parent')
            review(target)

    for path in paths:
        review(path)
    return {'passed': not errors, 'reviews': checked,
            'unique_file_bindings': len(claims), 'errors': errors}
