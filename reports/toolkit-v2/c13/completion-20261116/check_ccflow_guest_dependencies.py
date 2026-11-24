"""Temporary import projection shared by CCFlow intake review and the grader."""

import hashlib
import re
import tarfile
from pathlib import Path
from zipfile import ZipFile


def notice(path, filename, expected):
    data = path.with_name(filename).read_bytes()
    blob = f"blob {len(data)}\0".encode() + data
    if hashlib.sha1(blob, usedforsecurity=False).hexdigest() != expected:
        raise ValueError("publisher license notice differs from the upstream Git blob")
    return data


def entries(path):
    if path.name.endswith(".whl"):
        with ZipFile(path) as archive:
            result = {
                item.filename: archive.read(item)
                for item in archive.infolist()
                if not item.is_dir()
                and not any(part.endswith(".data") for part in Path(item.filename).parts)
            }
        if path.name == "cloudpickle-3.1.1-py3-none-any.whl":
            result["cloudpickle-3.1.1.dist-info/LICENSE.txt"] = notice(
                path,
                "cloudpickle-3.1.1-upstream-LICENSE.txt",
                "d112c4806aa90b4c911b360fa0ce1d0ee7c031ce",
            )
        return result
    if path.name != "antlr4-python3-runtime-4.9.3.tar.gz":
        raise ValueError("unreviewed source distribution")
    package = "antlr4-python3-runtime-4.9.3"
    dist = "antlr4_python3_runtime-4.9.3.dist-info"
    result = {}
    with tarfile.open(path, mode="r:gz") as archive:
        for item in archive:
            name = Path(item.name)
            if name.parts[:3] == (package, "src", "antlr4") and item.isfile():
                relative = Path(*name.parts[2:])
                if relative.suffix != ".py" or name.as_posix() != item.name or ".." in name.parts:
                    raise ValueError("unexpected ANTLR runtime member")
                result[relative.as_posix()] = archive.extractfile(item).read()
        metadata = archive.getmember(f"{package}/PKG-INFO")
        if not metadata.isfile():
            raise ValueError("ANTLR package metadata differs")
        result[f"{dist}/METADATA"] = archive.extractfile(metadata).read()
    result[f"{dist}/LICENSE.txt"] = notice(
        path,
        "antlr4-4.9.3-upstream-LICENSE.txt",
        "2042d1bda6c933e504d9dc2fe3197a6e42a71fe2",
    )
    if "antlr4/__init__.py" not in result:
        raise ValueError("ANTLR source layout changed")
    return result


def project(root, artifacts):
    target = root / "ccflow-imports"
    target.mkdir(mode=0o700)
    total = 0
    for filename, digest in artifacts.items():
        path = Path(filename)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        for name, data in entries(path).items():
            relative = Path(name)
            assert not relative.is_absolute() and ".." not in relative.parts
            total += max(4096, (len(data) + 4095) // 4096 * 4096)
            assert total <= 50 * 1024**2
            item = target / relative
            item.parent.mkdir(parents=True, exist_ok=True)
            with item.open("xb") as stream:
                stream.write(data)
            item.chmod(0o444)
    return target


def bootstrap_failure(log, code):
    with log.open("rb") as stream:
        stream.seek(max(0, log.stat().st_size - 4096))
        tail = stream.read().decode("utf-8", errors="replace")
    errors = re.findall(r"^([A-Za-z_][A-Za-z_0-9]*(?:Error|Exception))(?::|$)", tail, re.M)
    module = re.search(r"^ModuleNotFoundError: No module named '([A-Za-z0-9_.]+)'", tail, re.M)
    return {
        "phase": "pytest_bootstrap",
        "exit_code": code,
        "category": errors[-1] if errors else "MissingNativeEvent",
        "missing_module": module.group(1) if module else None,
    }
