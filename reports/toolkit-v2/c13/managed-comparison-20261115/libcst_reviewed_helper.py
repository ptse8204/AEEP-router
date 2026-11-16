"""Read-only optional LibCST check/rename preview inside the existing workspace."""

import argparse
import io
import os
import re
import stat
import sys
import tokenize
from pathlib import Path

ROOT = Path("/workspace")
CANDIDATE = Path("/opt/aeep-specialists")
MAX_SOURCE_BYTES = 350_000
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,12}\Z")


def read_source(relative):
    parts = relative.split("/")
    if (
        len(relative) > 300
        or not relative.endswith(".py")
        or not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}", part) for part in parts)
    ):
        raise ValueError("expected a relative Python source path")
    parent = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = directory
        with os.fdopen(
            os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent), "rb"
        ) as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size > MAX_SOURCE_BYTES
            ):
                raise ValueError("unsafe or oversized source file")
            data = source.read(MAX_SOURCE_BYTES + 1)
    finally:
        os.close(parent)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("source changed beyond the reviewed size bound")
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["check", "rename"])
    parser.add_argument("source")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    if args.operation == "check":
        if args.names:
            parser.error("check takes no names")
    elif len(args.names) != 2 or not all(NAME.fullmatch(name) for name in args.names):
        parser.error("rename requires two qualified names")
    source = read_source(args.source)
    sys.path.insert(0, str(CANDIDATE))
    import libcst

    if not Path(libcst.__file__).resolve().is_relative_to(CANDIDATE / "libcst"):
        raise ValueError("LibCST did not resolve to the reviewed package")
    module = libcst.parse_module(source)
    if args.operation == "check":
        print("LibCST parsed the selected source.")
        return 0
    from libcst.codemod import CodemodContext
    from libcst.codemod.commands.rename import RenameCommand

    changed = RenameCommand(CodemodContext(), *args.names).transform_module(module).code
    if changed == source:
        return 3  # Exact exit code identifies a completed transform with no edit.
    if len(changed.encode()) > MAX_SOURCE_BYTES:
        raise ValueError("preview exceeds the reviewed size bound")
    sys.stdout.write(changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
