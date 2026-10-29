"""Authored file guards and real ELF-data checks; no Linux code or image runs."""
import copy
import json
from pathlib import Path
import stat
import subprocess
import tempfile

from cached_context import NEEDED, OBJDUMP, parse_needed, sha, validate_files

HERE = Path(__file__).resolve().parent


def main():
    expected = json.loads((HERE / 'cached-context-audit.json').read_text())
    parent = json.loads((HERE / 'parent-ELF-audit.json').read_text())
    assert parent['loader_present_in_parent'] and parent['owned_export_and_ELF_scratch_removed_unchanged']
    checks = []
    with tempfile.TemporaryDirectory(prefix='aeep-authored-cached-context-') as temporary:
        root = Path(temporary)
        context, cache = root / 'context', root / 'cache'
        context.mkdir(mode=0o700)
        cache.mkdir(mode=0o700)
        (context / 'git').write_bytes(b'authored inert bytes')
        (context / 'git').chmod(0o555)
        (cache / 'git.deb').write_bytes(b'authored inert archive')
        sample = {'archive_bytes': (cache / 'git.deb').stat().st_size,
            'archive_sha256': sha(cache / 'git.deb'), 'context_files': {'git': sha(context / 'git')},
            'context_directories': {}}
        modes = {'git': 0o555}
        validate_files(context, cache, sample, modes)
        checks.append('exact_cached_files_pass')
        (context / 'extra').write_bytes(b'unreviewed')
        try:
            validate_files(context, cache, sample, modes)
        except AssertionError:
            pass
        else:
            raise AssertionError('Extra context file accepted')
        (context / 'extra').unlink()
        checks.append('extra_file_rejected')
        (context / 'git').chmod(0o755)
        try:
            validate_files(context, cache, sample, modes)
        except AssertionError:
            pass
        else:
            raise AssertionError('Changed mode accepted')
        (context / 'git').chmod(0o555)
        checks.append('mode_change_rejected')
        original = (context / 'git').read_bytes()
        (context / 'git').unlink()
        target = root / 'inert-target'
        target.write_bytes(original)
        (context / 'git').symlink_to(target)
        try:
            validate_files(context, cache, sample, modes)
        except AssertionError:
            pass
        else:
            raise AssertionError('Symlink context accepted')
        checks.append('symlink_rejected')
    assert not Path(temporary).exists()
    actual = parse_needed(expected['elf_inspection'])
    assert actual == NEEDED
    checks.append('actual_cached_ELF_includes_existing_loader')
    for altered in [expected['elf_inspection'].replace('ld-linux-aarch64.so.1', 'unreviewed.so.1'),
                    expected['elf_inspection'] + '\n  NEEDED unreviewed.so.1\n']:
        try:
            parse_needed(altered)
        except AssertionError:
            pass
        else:
            raise AssertionError('Altered dependency accepted')
    checks.append('different_or_extra_dependency_rejected')
    old = HERE.parent / 'repository-review-bindings-20261029'
    prior = json.loads((old / 'runtime-review.json').read_text())
    assert sha(OBJDUMP) == prior['upstream_metadata']['objdump_sha256']
    context = Path(expected['context'])
    text = subprocess.check_output([str(OBJDUMP), '-f', '-p', str(context / 'git')], text=True, timeout=20)
    assert text == expected['elf_inspection'] and parse_needed(text) == NEEDED
    modes = {str(path.relative_to(context)): stat.S_IMODE(path.stat().st_mode)
             for path in context.rglob('*') if path.is_file()}
    validate_files(context, Path(expected['archive']).parent, expected, modes)
    checks.append('actual_cache_context_and_static_ELF_unchanged')
    result = {'passed': True, 'checks': checks, 'inherited_loader_not_new_software': True,
        'authored_fixtures_removed': True, 'actual_context_unmodified': True,
        'downloads_builds_installs_containers_models_or_grant_charges': 0}
    with (HERE / 'cached-context-check.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({'passed': True, 'checks': len(checks)}))


if __name__ == '__main__':
    main()
