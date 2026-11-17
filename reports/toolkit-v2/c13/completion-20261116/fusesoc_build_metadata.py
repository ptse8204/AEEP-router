"""Reconstruct one pinned FuseSoC snapshot's omitted setuptools-scm metadata."""

import tomllib
from pathlib import Path


def generate_version_file(tree, support, binding):
    """Called inside the protected worker before pytest can import the subject."""
    from setuptools_scm import get_version
    from setuptools_scm.version import meta

    if not Path(get_version.__code__.co_filename).is_relative_to(support):
        raise ValueError("version renderer did not come from the reviewed support tree")
    pyproject = tomllib.loads((tree / "pyproject.toml").read_text())
    config = pyproject["tool"]["setuptools_scm"]
    if config != {"write_to": "fusesoc/version.py"}:
        raise ValueError("upstream version generation configuration changed")
    target = tree / config["write_to"]
    if target.exists() or target.is_symlink():
        raise ValueError("upstream snapshot already has a version module")

    def reviewed_scm(root, config):
        if Path(root) != tree:
            raise ValueError("SCM callback received another source tree")
        return meta(
            binding["tag"],
            distance=binding["distance"],
            node="g" + binding["revision"],
            dirty=False,
            config=config,
        )

    version = get_version(
        root=tree, write_to=config["write_to"], parse=reviewed_scm, dist_name="fusesoc"
    )
    if version != binding["expected_version"] or not target.is_file() or target.is_symlink():
        raise ValueError("upstream version renderer did not write the expected metadata")
    return version
