"""Synthetic archive safety controls; no external download/package/build runs."""
import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reviewed_vendor', HERE / 'vendor.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def archive(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as out:
        for name, content, kind in entries:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            if kind == tarfile.SYMTYPE:
                entry.linkname = '/outside'
            else:
                entry.size = len(content)
            out.addfile(entry, io.BytesIO(content))
    return data.getvalue()


rows = []
manifest = b'[package]\nname="fixture"\nversion="1.0.0"\nlicense="MIT OR Apache-2.0"\n'
valid = [('fixture-1.0.0/Cargo.toml', manifest, tarfile.REGTYPE),
         ('fixture-1.0.0/src/lib.rs', b'// first-party control\n', tarfile.REGTYPE)]
with tempfile.TemporaryDirectory(prefix='aeep-vendor-safety-') as work:
    root = Path(work)
    raw = archive(valid)
    result = module.unpack(raw, name='fixture', version='1.0.0',
        expected=hashlib.sha256(raw).hexdigest(), destination=root / 'valid')
    checksum = json.loads((root / 'valid/.cargo-checksum.json').read_text())
    assert checksum['files']['Cargo.toml'] == hashlib.sha256(manifest).hexdigest()
    assert result['license_expression'] == 'MIT OR Apache-2.0'
    rows.append('valid source/checksum/license; no package execution')
    for index, additions in enumerate([
        [('fixture-1.0.0/../../outside', b'bad', tarfile.REGTYPE)],
        [('/absolute', b'bad', tarfile.REGTYPE)],
        [('other-1.0.0/Cargo.toml', b'bad', tarfile.REGTYPE)],
        [('fixture-1.0.0/link', b'', tarfile.SYMTYPE)],
        [valid[0]],
        [('fixture-1.0.0/.cargo-checksum.json', b'bad', tarfile.REGTYPE)],
    ]):
        raw = archive(valid + additions)
        try:
            module.unpack(raw, name='fixture', version='1.0.0',
                expected=hashlib.sha256(raw).hexdigest(), destination=root / ('unsafe-' + str(index)))
        except ValueError:
            assert not (root / ('unsafe-' + str(index))).exists()
            rows.append('unsafe archive rejected before writes: ' + str(index))
        else:
            raise AssertionError('Unsafe fixture accepted')
    try:
        module.unpack(archive(valid), name='fixture', version='1.0.0', expected='0'*64,
                      destination=root / 'wrong-checksum')
    except ValueError:
        assert not (root / 'wrong-checksum').exists()
        rows.append('incorrect checksum rejected before writes')
    else:
        raise AssertionError('Wrong hash accepted')
payload = {'passed': True, 'controls': rows, 'count': len(rows), 'models': 0,
           'actual_Cargo_sources_executed': False, 'actual_downloads': 0}
(HERE / 'vendor-controls.json').write_text(json.dumps(payload, indent=2) + '\n')
print(json.dumps(payload))
