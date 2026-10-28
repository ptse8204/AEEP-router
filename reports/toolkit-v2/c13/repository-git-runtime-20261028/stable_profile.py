"""Compile a contained-only workspace profile; never accept a runtime host path."""
import ast

REPOSITORY = '/tmp/aeep-repository-native-v6'


def compile_profile(program):
    old = "        repo = root / 'repository'\n        repo.mkdir()"
    new = "        repo = Path(" + repr(REPOSITORY) + ")\n        repo.mkdir(mode=0o700)"
    if program.count(old) != 1:
        raise ValueError('Expected one exact repository creation site')
    compiled = program.replace(old, new)
    # Freeze the only changes: repository assignment and its exclusive mkdir.
    before, after = ast.parse(program), ast.parse(compiled)
    original = [n for n in ast.walk(before) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'repo' for t in n.targets)]
    changed = [n for n in ast.walk(after) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'repo' for t in n.targets)]
    assert len(original) == len(changed) == 1
    changed[0].value = original[0].value
    mkdirs = [n for n in ast.walk(after) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr == 'mkdir'
              and isinstance(n.func.value, ast.Name) and n.func.value.id == 'repo']
    assert len(mkdirs) == 1 and len(mkdirs[0].keywords) == 1
    mkdirs[0].keywords = []
    assert ast.dump(before) == ast.dump(after)
    return compiled
