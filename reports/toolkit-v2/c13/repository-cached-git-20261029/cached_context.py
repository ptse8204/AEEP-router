"""Verify the already prepared Git component; never download or modify its context."""
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

HERE = Path(__file__).resolve().parent
NEEDED = {'libc.so.6', 'libpcre2-8.so.0', 'libz.so.1', 'ld-linux-aarch64.so.1'}
OBJDUMP = Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/llvm-objdump')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_files(context, cache, expected, modes):
    archive = cache / 'git.deb'
    assert archive.is_file() and not archive.is_symlink()
    assert archive.stat().st_size == expected['archive_bytes'] and sha(archive) == expected['archive_sha256']
    assert context.is_dir() and not context.is_symlink()
    paths = list(context.rglob('*'))
    assert all(not path.is_symlink() for path in paths)
    assert {str(path.relative_to(context)): sha(path) for path in paths if path.is_file()} == expected['context_files']
    assert {str(path.relative_to(context)): stat.S_IMODE(path.stat().st_mode) for path in paths if path.is_dir()} == expected['context_directories']
    assert stat.S_IMODE(context.stat().st_mode) == 0o700
    assert {str(path.relative_to(context)): stat.S_IMODE(path.stat().st_mode) for path in paths if path.is_file()} == modes


def parse_needed(text):
    assert 'elf64-littleaarch64' in text
    needed = set(re.findall(r'^\s*NEEDED\s+(\S+)\s*$', text, re.MULTILINE))
    assert needed == NEEDED, 'Unexpected dependency; do not build or add software'
    return needed


def verify(context, cache, metadata):
    review = json.loads((HERE / 'runtime-review.json').read_text())
    expected = json.loads((HERE / 'cached-context-audit.json').read_text())
    parent = json.loads((HERE / 'parent-ELF-audit.json').read_text())
    assert parent['passed'] and parent['loader_present_in_parent']
    assert parent['image_id'] == review['parent_image']
    assert context.resolve() == Path(expected['context']).resolve()
    assert (cache / 'git.deb').resolve() == Path(expected['archive']).resolve()
    validate_files(context, cache, expected, review['context_mode_pins'])
    assert sha(OBJDUMP) == metadata['objdump_sha256']
    text = subprocess.check_output([str(OBJDUMP), '-f', '-p', str(context / 'git')], text=True, timeout=20)
    needed = parse_needed(text)
    assert text == expected['elf_inspection']
    assert sha(context / 'git') == parent['git_binary_sha256']
    assert sha(context / 'copyright') == metadata['copyright_sha256']
    return {'package_sha256': expected['archive_sha256'], 'package_bytes': expected['archive_bytes'],
        'requests': [], 'new_downloads': 0, 'cache_reused_unchanged': True,
        'needed_libraries': sorted(needed), 'elf_inspection': text,
        'inherited_loader_evidence': parent['ELF_files'][parent['loader_canonical_path']],
        'context_files': expected['context_files'], 'linux_binary_executed_on_host': False,
        'maintainer_scripts_executed': False, 'source_binary_redistributed': False}
