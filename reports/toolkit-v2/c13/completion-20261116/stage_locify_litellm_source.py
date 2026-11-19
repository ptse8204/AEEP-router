"""Retain and verify the publisher's source after the locked wheel disappeared."""

import argparse
import ast
import gzip
import hashlib
import io
import json
import shutil
import tarfile
import tomllib
from pathlib import PurePosixPath
from urllib.request import urlopen

from stage_repository_transport import ROOT, WORK, digest, encode, write

REVISION = "fb523b79e9fdd7ce2d3a33f6c57a3679c7249e35"
TREE = "86f15483a24629bc3dfbb987840e240d9e4ef875"
TREE_PIN = "3fafa4b2f3e704daf4b66458343446a23ee11444065f449b27505ff1cfd0d860"
TREE_URL = f"https://api.github.com/repos/BerriAI/litellm/git/trees/{TREE}?recursive=1"
ARCHIVE_URL = f"https://codeload.github.com/BerriAI/litellm/tar.gz/{REVISION}"
ARCHIVE_LIMIT = 64 * 1024**2
EXPANSION_LIMIT = 128 * 1024**2
HOST_RESERVE = 50 * 1024**3
ROOT_FILES = {"LICENSE", "pyproject.toml"}
EXPECTED_LINKS = {
    "litellm/proxy/enterprise": "../../enterprise",
    "litellm/requirements.txt": "../requirements.txt",
}
OUTPUT = WORK / "locify-litellm-publisher-source-20261119"


def fetch(url, limit):
    with urlopen(url, timeout=20) as response:
        if response.geturl() != url:
            raise ValueError("publisher request redirected")
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("publisher response exceeds the reviewed bound")
    return raw


def selected_tree(raw):
    tree = json.loads(raw)
    if digest(raw) != TREE_PIN or tree["sha"] != TREE or tree["truncated"]:
        raise ValueError("publisher tree changed")
    chosen = {item["path"]: item for item in tree["tree"]
              if item["type"] == "blob" and (
                  item["path"] in ROOT_FILES or item["path"].startswith("litellm/"))}
    if len(chosen) != 463 or ROOT_FILES.difference(chosen):
        raise ValueError("publisher package selection changed")
    links = {path for path, item in chosen.items() if item["mode"] == "120000"}
    if links != EXPECTED_LINKS.keys():
        raise ValueError("publisher symlink set changed")
    return chosen


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def package_members(raw, selected):
    package = {}
    prefix = f"litellm-{REVISION}"
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        body = compressed.read(EXPANSION_LIMIT + 1)
    if len(body) > EXPANSION_LIMIT:
        raise ValueError("publisher archive exceeds the expanded bound")
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:") as tar:
        for member in tar:
            parts = PurePosixPath(member.name)
            if (not parts.parts or parts.parts[0] != prefix
                    or str(parts) != member.name or ".." in parts.parts):
                raise ValueError("publisher archive path changed")
            name = str(PurePosixPath(*parts.parts[1:]))
            if name not in selected:
                continue
            if name in package:
                raise ValueError("duplicate publisher package member")
            item = selected[name]
            if name in EXPECTED_LINKS:
                if not member.issym() or member.linkname != EXPECTED_LINKS[name]:
                    raise ValueError("publisher symlink changed")
                data = member.linkname.encode()
            else:
                if not member.isfile() or member.size != item["size"]:
                    raise ValueError("publisher package member changed type or size")
                data = tar.extractfile(member).read()
            if len(data) != item["size"] or git_blob(data) != item["sha"]:
                raise ValueError("publisher package bytes differ from the exact Git tree")
            package[name] = data
    if package.keys() != selected.keys():
        raise ValueError("publisher archive omitted package members")
    return package


def function_source(source, name):
    body = source.decode()
    function, = [node for node in ast.parse(body).body
                 if isinstance(node, ast.FunctionDef) and node.name == name]
    raw = ast.get_source_segment(body, function).encode()
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-publisher-source", action="store_true", required=True)
    parser.parse_args()
    if OUTPUT.exists() or shutil.disk_usage(ROOT).free < HOST_RESERVE + ARCHIVE_LIMIT + 8 * 1024**2:
        raise ValueError("source intake needs an unstarted directory and sufficient space")
    tree = fetch(TREE_URL, 1024**2)
    selected = selected_tree(tree)
    archive = fetch(ARCHIVE_URL, ARCHIVE_LIMIT)
    members = package_members(archive, selected)
    metadata = tomllib.loads(members["pyproject.toml"].decode())
    project = metadata["tool"]["poetry"]
    if project["version"] != "1.50.1" or project["license"] != "MIT" or b"MIT License" not in members["LICENSE"]:
        raise ValueError("publisher version or license changed")
    utils = members["litellm/utils.py"]
    token_counter = function_source(utils, "token_counter")
    openai_counter = function_source(utils, "openai_token_counter")
    price_map = function_source(members["litellm/__init__.py"], "get_model_cost_map")
    if (b"openai_token_counter(" not in token_counter or b"o200k_base" not in openai_counter
            or b"LITELLM_LOCAL_MODEL_COST_MAP" not in price_map):
        raise ValueError("expected offline tokenizer support changed")
    if shutil.disk_usage(ROOT).free < HOST_RESERVE + len(archive) + 2 * 1024**2:
        raise ValueError("storage changed during source acquisition")
    OUTPUT.mkdir(mode=0o700)
    artifact = OUTPUT / f"{REVISION}.tar.gz"
    write(artifact, archive)
    write(OUTPUT / "git-tree.json", tree)
    write(OUTPUT / "verification.json", encode({
        "publisher_revision": REVISION,
        "publisher_git_tree": TREE,
        "publisher_git_tree_source": TREE_URL,
        "publisher_git_tree_sha256": TREE_PIN,
        "archive_url": ARCHIVE_URL,
        "archive": {"path": str(artifact.relative_to(ROOT)), "bytes": len(archive), "sha256": digest(archive)},
        "verified_package_members": len(members),
        "verified_symlinks_retained_in_inert_archive": EXPECTED_LINKS,
        "package_source_bytes": sum(map(len, members.values())),
        "license_sha256": digest(members["LICENSE"]),
        "project_metadata_sha256": digest(members["pyproject.toml"]),
        "token_counter_sha256": digest(token_counter),
        "openai_token_counter_sha256": digest(openai_counter),
        "local_price_map_function_sha256": digest(price_map),
        "source_build_backend": metadata["build-system"],
        "scope": "Publisher source verified by Git blob. This archive differs from the unavailable locked distribution.",
        "native_builds": 0,
        "packages_executed": 0,
        "grader_invocations": 0,
        "model_turns": 0,
    }))
    print(f"Verified {len(members)} package members in a {len(archive)}-byte publisher archive.")


if __name__ == "__main__":
    main()
