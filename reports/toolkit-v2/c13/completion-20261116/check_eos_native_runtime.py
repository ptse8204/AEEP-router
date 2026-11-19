"""Assemble the exact EOS runtime in the retained ordinary Linux carrier."""

import argparse
import asyncio
import io
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import check_locify_source_wheels as journal
from stage_repository_transport import ROOT, WORK, encode, read, write

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore

NAME = "c13-eos-native-runtime-20261119"
TARGET = WORK / NAME
CONTEXT = TARGET / "context"
REVIEW = TARGET / "operation-review.json"
DOWNLOADS = WORK / "eos-resolved-runtime-assets-20261119/result.json"
QUOTE = WORK / "full-rebench-three-leads-20261119/retained-reference-assets/eos-resolved-asset-quote-20261119.json"
GRADER = "aeep-toolkit-v2/repository-grader:py313-shared-native-git-20261028"
PYTHON_ROOT = "/opt/portable/python"
VENV = "/opt/c13-eos"
TAG = "aeep-toolkit-v2/eos-runtime:d912561b-cp312-20261119"
ZSTD = Path("/usr/local/bin/zstd")
THRESHOLD = 53 * 2**30
LIMITS = AssessmentLimits(max_operations=2, max_elapsed_seconds=465)

PROBE = """import importlib, importlib.metadata, json, sys
from pathlib import Path

prefix = Path('/opt/c13-eos')
assert Path(sys.prefix) == prefix and sys.version_info[:2] == (3, 12)
expected = dict(line.split('==', 1) for line in Path('/opt/c13-eos-input/versions.txt').read_text().splitlines())
for name, version in expected.items():
    assert importlib.metadata.version(name) == version, name
modules = {}
for name in ('apsw', 'h3', 'h5py', 'numpy', 'pandas', 'pendulum', 'pvlib', 'pytest',
             'scipy', 'sklearn', 'statsmodels', 'time_machine', 'timezonefinder', 'xprocess'):
    module = importlib.import_module(name)
    assert Path(module.__file__).is_relative_to(prefix), name
    modules[name] = str(Path(module.__file__).relative_to(prefix))
from timezonefinder import TimezoneFinder
assert TimezoneFinder().timezone_at(lng=-123.1207, lat=49.2827) == 'America/Vancouver'
print(json.dumps({'native_imports': modules, 'versions': len(expected), 'timezone_lookup': True}))
"""


def inventory():
    paths = {}
    for path in CONTEXT.rglob("*"):
        if path.is_symlink():
            raise ValueError("build context cannot contain symlinks")
        if path.is_file():
            paths[str(path.relative_to(CONTEXT))] = journal.fingerprint(path)
    return paths


def native_members(blob):
    with ZipFile(io.BytesIO(blob)) as package:
        inner, = [name for name in package.namelist() if name.startswith("pkg-") and name.endswith(".tar.zst")]
        compressed = package.read(inner)
    unpacked = subprocess.run([str(ZSTD), "-dc", "--memory=128MiB"], input=compressed,
                              capture_output=True, check=True, timeout=15).stdout
    members = {}
    links = {}
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.name in members or member.name in links:
                raise ValueError("unsafe or duplicate Conda member")
            if member.isfile():
                stream = tar.extractfile(member)
                if stream is None:
                    raise ValueError("readable Conda member required")
                members[member.name] = stream.read()
            elif member.issym():
                links[member.name] = member.linkname
            elif not member.isdir():
                raise ValueError("unexpected Conda tar member type")
    return members, links


def project_native(conda):
    timezone, links = conda["timezonefinder"]
    root = "lib/python3.12/site-packages/"
    if links:
        raise ValueError("timezone package contains unexpected links")
    output = {
        "site/" + name.removeprefix(root): data for name, data in timezone.items()
        if name.startswith(root) and not name.endswith(".pyc")
    }
    gcc, _ = conda["libgcc"]
    omp, _ = conda["libgomp"]
    mutex, aliases = conda["_openmp_mutex"]
    if aliases != {"lib/libgomp.so.1": "libgomp.so.1.0.0"}:
        raise ValueError("reviewed native alias changed")
    for name, data in {"libgcc_s.so.1": gcc["lib/libgcc_s.so.1"],
                       "libgomp.so.1": omp["lib/libgomp.so.1.0.0"]}.items():
        if data[:6] != b"\x7fELF\x02\x01" or int.from_bytes(data[18:20], "little") != 183:
            raise ValueError("native dependency is not ARM64 ELF")
        output["native/" + name] = data
    for package, paths in (("timezonefinder", timezone), ("libgcc", gcc), ("libgomp", omp), ("openmp", mutex)):
        for name, data in paths.items():
            if name.startswith(("info/licenses/", "share/licenses/")):
                output[f"notices/{package}/{name}"] = data
    if len([x for x in output if x.startswith("notices/")]) < 4:
        raise ValueError("Conda license notices are incomplete")
    return output


def commands():
    docker, env = journal.docker_settings()
    build = [*docker, "build", "--pull=false", "--network=none", "--platform=linux/arm64",
             "--provenance=false", "--sbom=false", "--tag", TAG, str(CONTEXT)]
    return docker, env, build


def prepare():
    if REVIEW.exists() or shutil.disk_usage(ROOT).free < THRESHOLD:
        raise ValueError("first runtime review requires unstarted scope and free space")
    quote = journal.doc(QUOTE)
    acquired = journal.doc(DOWNLOADS)
    records = quote["exact_cached"] | {row["name"]: row for row in acquired["artifacts"]}
    selected = {name: row["artifact"]["sha256"] for name, row in quote["selected"].items()}
    closure = journal.doc(Path(__file__).with_name("eos-runtime-closure-20261119.json"))
    selected.update({name: row["sha256"] for name, row in closure["selected_conda_native_packages"].items()})
    if records.keys() != selected.keys() or len(records) != 71:
        raise ValueError("artifact closure changed")
    conda = {}
    requirements = []
    for name, record in sorted(records.items()):
        path = ROOT / record["path"]
        data = read(path, selected[name])
        if len(data) != record["bytes"]:
            raise ValueError("pinned artifact size changed")
        if path.suffix == ".conda":
            conda[name] = native_members(data)
        else:
            version = quote["selected"][name]["version"]
            with ZipFile(io.BytesIO(data)) as archive:
                if not any(entry.endswith(".dist-info/METADATA") for entry in archive.namelist()):
                    raise ValueError("wheel metadata missing")
            write(CONTEXT / "wheels" / path.name, data)
            requirements.append(f"{name}=={version} --hash=sha256:{selected[name]}")
    if len(requirements) != 67 or len(conda) != 4:
        raise ValueError("EOS runtime wheel or native count differs")
    for path, content in project_native(conda).items():
        write(CONTEXT / path, content)
    write(CONTEXT / "requirements.txt", ("\n".join(requirements) + "\n").encode())
    versions = sorted(f"{name}=={row['version']}" for name, row in quote["selected"].items())
    write(CONTEXT / "versions.txt", ("\n".join(versions) + "\n").encode())
    compile(PROBE, "<EOS import probe>", "exec")
    write(CONTEXT / "probe.py", PROBE.encode())
    python = VENV + "/bin/python"
    site = VENV + "/lib/python3.12/site-packages"
    recipe = [
        f"FROM {journal.BASE} AS portable",
        f"FROM {GRADER}",
        "USER 0:0",
        f"COPY --from=portable {PYTHON_ROOT}/ {PYTHON_ROOT}/",
        "COPY wheels/ /opt/c13-eos-input/wheels/",
        "COPY requirements.txt versions.txt probe.py /opt/c13-eos-input/",
        f'RUN ["{PYTHON_ROOT}/bin/python3.12","-I","-B","-m","venv","{VENV}"]',
        "RUN " + json.dumps([python, "-I", "-B", "-m", "pip", "--isolated", "install",
                             "--no-index", "--no-deps", "--disable-pip-version-check", "--no-compile",
                             "--require-hashes", "--find-links=/opt/c13-eos-input/wheels",
                             "-r", "/opt/c13-eos-input/requirements.txt"]),
        f"COPY site/ {site}/",
        "COPY native/ /opt/c13-eos-native/",
        "COPY notices/ /opt/c13-eos-notices/",
        "USER 65534:65534",
        "WORKDIR /tmp",
        "",
    ]
    write(CONTEXT / "Dockerfile", "\n".join(recipe).encode())
    docker, env, build = commands()
    sources = {name: journal.inspect(docker, env, name) for name in (journal.BASE, GRADER)}
    if sources[journal.BASE]["id"] != journal.BASE_ID:
        raise ValueError("retained Python carrier changed")
    usage = subprocess.check_output([*docker, "system", "df"], env=env, text=True, timeout=25)
    write(REVIEW, encode({
        "schema_version": "aeep.c13.eos-first-native-runtime.v1",
        "context": inventory(), "sources": sources, "manifest": selected,
        "quote_sha256": journal.fingerprint(QUOTE), "acquisition_sha256": journal.fingerprint(DOWNLOADS),
        "source_build_driver_sha256": journal.fingerprint(Path(journal.__file__)),
        "driver_sha256": journal.fingerprint(Path(__file__)),
        "standing_authority_sha256": journal.fingerprint(journal.AUTHORITY),
        "docker": docker, "env": env, "build": build, "docker_pins": journal.docker_pins(docker),
        "docker_usage": usage, "tag": TAG, "parent": GRADER,
        "expires_at": (utc_now() + timedelta(hours=2)).isoformat(),
        "max_operations": LIMITS.max_operations, "max_reserved_seconds": LIMITS.max_elapsed_seconds,
        "models": 0, "cash_usd": 0, "downloads": 0, "protected_case_runs": 0, "automatic_retry": False,
    }))
    print(journal.fingerprint(REVIEW))


def preflight(exact):
    review = journal.doc(REVIEW)
    expiry = datetime.fromisoformat(review["expires_at"])
    docker, env, build = commands()
    if (journal.fingerprint(REVIEW) != exact or (TARGET / "started.json").exists()
            or shutil.disk_usage(ROOT).free < THRESHOLD or utc_now() >= expiry
            or review["context"] != inventory() or review["docker_pins"] != journal.docker_pins(docker)
            or review["docker"] != docker or review["env"] != env or review["build"] != build
            or journal.fingerprint(Path(__file__)) != review["driver_sha256"]
            or journal.fingerprint(Path(journal.__file__)) != review["source_build_driver_sha256"]
            or journal.fingerprint(journal.AUTHORITY) != review["standing_authority_sha256"]
            or journal.fingerprint(QUOTE) != review["quote_sha256"]
            or journal.fingerprint(DOWNLOADS) != review["acquisition_sha256"]
            or any(journal.inspect(docker, env, name) != identity for name, identity in review["sources"].items())
            or subprocess.run([*docker, "image", "inspect", TAG], env=env, capture_output=True,
                              timeout=10).returncode == 0):
        raise ValueError("first runtime scope or tool binding changed")
    return review, expiry, docker, env, build


async def execute(exact):
    review, expiry, docker, env, build = await asyncio.to_thread(preflight, exact)
    scope = journal.Scope(review_sha256=exact)
    key = content_digest(scope)
    request = RecipeMaterializationRequest(plan_id=NAME, authorization_id=NAME, subject_digest=key,
        recipe_digest=key, mapping_digest=key, environment_digest=key, definition_digests=[key], seed=0)
    grant = AssessmentAuthorization(authorization_id=NAME, subject_digests=[key], recipe_digests=[key],
        environment_digests=[key], allowed_destinations=["local"], expires_at=expiry, limits=LIMITS,
        remote_disclosure=False)
    write(TARGET / "started.json", encode({"review": exact, "first_attempt": True,
                                         "authority": str(journal.AUTHORITY.relative_to(ROOT))}))
    journal.HOME_DIR, journal.LABEL = TARGET, NAME
    result = {"passed": False, "review_sha256": exact}
    with ReceiptStore(TARGET / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_runtime_scope", key, scope)
        repo.approve_bundle(grant, {key: scope.model_dump(mode="json")})
        try:
            await journal.run_operation(repo, store, request, build, "offline-build", 350, exact, env)
            image = journal.inspect(docker, env, TAG)
            parent = review["sources"][GRADER]["layers"]
            if image["layers"][:len(parent)] != parent:
                raise ValueError("new image did not inherit the known ordinary carrier")
            result["image"] = image
            probe = [*docker, "run", "--pull=never", "--rm", "--name", NAME + "-probe",
                     "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                     "--user=65534:65534", "--memory=1024m", "--memory-swap=1024m", "--pids-limit=96",
                     "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m",
                     "--env=LD_LIBRARY_PATH=/opt/c13-eos-native", "--env=OPENBLAS_NUM_THREADS=1",
                     "--entrypoint", VENV + "/bin/python", image["id"], "-I", "-B", "/opt/c13-eos-input/probe.py"]
            result["probe_argv_sha256"] = content_digest({"argv": probe})
            raw = await journal.run_operation(repo, store, request, probe, "offline-import-probe", 100, exact, env)
            reply = json.loads(raw.stdout)
            if reply["versions"] != 68 or reply["timezone_lookup"] is not True or len(reply["native_imports"]) != 14:
                raise ValueError("native imports or compatibility check did not pass")
            result["observations"] = reply
            result["passed"] = True
        finally:
            write(TARGET / "ledger.json", encode(repo.operation_ledger(NAME).model_dump(mode="json")))
            write(TARGET / "result.json", encode(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--first-review")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        asyncio.run(execute(args.first_review))


if __name__ == "__main__":
    main()
