"""Prepare content-bound Formula Extraction and A2A retry inputs as inert files."""

import hashlib
import shutil
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import run_a2a_batch as previous
from check_linux_install import HERE, ROOT, WORK, get, put

from aeep.assessment.models import content_digest
from aeep_toolkit.install_runtime import file_digest

FORMULA_WORK = WORK / "formula-offline-assets"
REACT_REVIEW = HERE.parent / "skillsbench-react-readonly-grader-20261108/operation-review.json"
A2A_CASE = "a2aproject__a2a-python-472"
RESERVE = 52 * 1024**3
STAGING_LIMIT = 650 * 1024**2


def tree(root):
    if root.is_symlink() or root.resolve() != root or not root.is_dir():
        raise ValueError("protected root is not a canonical directory")
    rows = {}
    for path in (root, *sorted(root.rglob("*"))):
        data = path.lstat()
        mode = stat.S_IMODE(data.st_mode)
        if stat.S_ISDIR(data.st_mode):
            rows[str(path)] = {"mode": mode}
        elif stat.S_ISREG(data.st_mode):
            rows[str(path)] = {"mode": mode, "sha256": file_digest(path)}
        else:
            raise ValueError("unexpected protected input type")
    return rows


def verify_bootstrap():
    review = get(REACT_REVIEW)
    receipt = get(REACT_REVIEW.with_name("result.json"))
    assert receipt["passed"] is True and receipt["review_sha256"] == file_digest(REACT_REVIEW)
    env_path = REACT_REVIEW.with_name("environment.json")
    assert file_digest(env_path) == review["pins"][str(env_path)]
    environment = get(env_path)
    bootstrap = Path(environment["read_only_roots"][0])
    assert bootstrap.name == "python" and bootstrap.is_relative_to(ROOT / ".aeep")
    inventory = ROOT / ".aeep/skillsbench-react-readonly-grader-20261108/mount-inventory.json"
    assert file_digest(inventory) == review["pins"][str(inventory)]
    required = {
        path: row for path, row in get(inventory).items() if Path(path).is_relative_to(bootstrap)
    }
    assert tree(bootstrap) == required
    return bootstrap, environment, file_digest(REACT_REVIEW)


def expanded_size(archive):
    with ZipFile(archive) as package:
        return sum(member.file_size for member in package.infolist())


def extract(archive, root, *, existing):
    """Copy only reviewed normal entries. Preserve executable permission, not archive owners."""
    files = set()
    with ZipFile(archive) as package:
        seen = set()
        for member in package.infolist():
            spec = PurePosixPath(member.filename)
            check = spec.as_posix() + ("/" if member.is_dir() else "")
            raw_mode = member.external_attr >> 16
            if (
                spec.is_absolute()
                or not spec.parts
                or check != member.filename
                or ".." in spec.parts
                or "\\" in member.filename
                or spec in seen
                or stat.S_IFMT(raw_mode)
                not in {0, stat.S_IFDIR if member.is_dir() else stat.S_IFREG}
            ):
                raise ValueError("unsafe archive member")
            seen.add(spec)
            out = root.joinpath(*spec.parts)
            if member.is_dir():
                if not existing:
                    out.mkdir(mode=0o755, parents=True, exist_ok=True)
                continue
            files.add(out)
            mode = 0o555 if raw_mode & 0o111 else 0o444
            if existing:
                with package.open(member) as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if (
                    out.is_symlink()
                    or not out.is_file()
                    or stat.S_IMODE(out.stat().st_mode) != mode
                    or file_digest(out) != digest
                ):
                    raise ValueError("existing prepared archive member differs")
            else:
                out.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                with package.open(member) as stream, out.open("xb") as handle:
                    shutil.copyfileobj(stream, handle, length=1024 * 1024)
                out.chmod(mode)
    return files


def freeze(root):
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o555)
        elif path.is_file():
            mode = path.stat().st_mode
            path.chmod(0o555 if mode & 0o111 else 0o444)
        else:
            raise ValueError("non-regular staged file")
    root.chmod(0o555)


def stage_formula(root):
    evidence = get(HERE / "formula-runtime-acquisition-result.json")
    acquired = FORMULA_WORK / "acquired"
    for artifact in evidence["received"]:
        archived = acquired / artifact["file"]
        assert (
            archived.stat().st_size == artifact["bytes"]
            and file_digest(archived) == artifact["sha256"]
        )
    assert evidence["executed"] is evidence["installed"] is False
    support = get(FORMULA_WORK / "support-lock.json")
    report = get(HERE / "formula-offline-preparation.json")
    assert file_digest(FORMULA_WORK / "support-lock.json") == report["wheel_closure"]["lock_sha256"]
    wheels = {name: (ROOT / row["path"], row["sha256"]) for name, row in support["wheels"].items()}
    for path, sha in wheels.values():
        assert file_digest(path) == sha
    (browser,) = [
        acquired / row["file"] for row in evidence["received"] if row["file"].endswith(".zip")
    ]
    expanded = sum(expanded_size(path) for path in [browser, *(row[0] for row in wheels.values())])
    if expanded > STAGING_LIMIT or shutil.disk_usage(root.parent).free < RESERVE + expanded:
        raise ValueError("prepared renderer exceeds its storage reserve")
    original = FORMULA_WORK / "protected-fixtures"
    lock = get(original / "protected-fixture-lock.json")
    assert (
        file_digest(original / "protected-fixture-lock.json")
        == report["fixtures"]["protected_lock_sha256"]
    )
    assert all(file_digest(original / name) == digest for name, digest in lock["files"].items())
    worker = HERE / "formula_reference_guest.py"
    assert file_digest(worker) == report["fixtures"]["guest_sha256"]
    bootstrap, carrier, previous_review = verify_bootstrap()
    assert carrier["container_image"] == report["carrier"]["id"]

    existing = root.exists()
    payload = root / "renderer"
    if existing:
        assert list(root.iterdir()) == [payload]
        staged = tree(payload)
    else:
        root.mkdir(mode=0o700)
        payload.mkdir(mode=0o755)
        shutil.copytree(original, payload / "protected-fixtures")
        shutil.copyfile(worker, payload / "guest.py")
    fixed = {payload / "guest.py": file_digest(worker)}
    fixed.update(
        {payload / "protected-fixtures" / name: digest for name, digest in lock["files"].items()}
    )
    fixed[payload / "protected-fixtures/protected-fixture-lock.json"] = file_digest(
        original / "protected-fixture-lock.json"
    )
    assert all(file_digest(path) == digest for path, digest in fixed.items())
    expected_files = set(fixed)
    for wheel, _ in wheels.values():
        expected_files.update(extract(wheel, payload / "support", existing=existing))
    browser_dir = payload / "browsers/chromium_headless_shell-1200"
    expected_files.update(extract(browser, browser_dir, existing=existing))
    if existing:
        assert {Path(path) for path, data in staged.items() if "sha256" in data} == expected_files
    chromium = browser_dir / "chrome-headless-shell-linux64/chrome-headless-shell"
    node = payload / "support/playwright/driver/node"
    for path in (chromium, node):
        with path.open("rb") as binary:
            header = binary.read(20)
        assert header[:6] == b"\x7fELF\x02\x01" and header[18:20] == bytes((62, 0))
        assert path.stat().st_mode & 0o111
    # Playwright's browser registry selects this exact Linux executable path.
    registry = (
        payload / "support/playwright/driver/package/lib/server/registry/index.js"
    ).read_text()
    assert '"linux-x64": ["chrome-headless-shell-linux64", "chrome-headless-shell"]' in registry
    assert 'browserDirectoryPrefix.replace(/-/g, "_") + "-" + revision' in registry
    dist = payload / "support/playwright-1.57.0.dist-info/licenses/LICENSE"
    assert dist.is_file() and dist.stat().st_size > 0
    if not existing:
        freeze(payload)
    return {
        "carrier": carrier,
        "bootstrap": str(bootstrap),
        "previous_runtime_review": previous_review,
        "artifact_bytes_expanded": expanded,
        "wheel_count": len(wheels),
        "playwright_license_sha256": file_digest(dist),
        "roles": list(lock["roles"]),
        "identity_count": len(lock["identities"]),
        "guest_binaries_executed": False,
        "sha256_by_staged_root": {
            str(payload): content_digest(tree(payload)),
            str(bootstrap): content_digest(tree(bootstrap)),
        },
    }


def stage_a2a(root):
    results = get(HERE / "approved-a2a-batch-results.json")
    assert file_digest(previous.REVIEW) == results["review_sha256"]
    assert results["settled_operations"] == 5 and set(results["roles"][A2A_CASE]) == {"reference"}
    assert results["roles"][A2A_CASE]["reference"]["upstream_exit_code"] == 4
    diagnostics = results["a2a_472_static_diagnosis"]["roles"]
    original_review = get(previous.REVIEW)
    shared = previous.SHARED
    old_inventory = original_review["files"]
    actual = {
        Path(path).relative_to(previous.MOUNT).as_posix(): row["sha256"]
        for path, row in tree(shared).items()
        if "sha256" in row
    }
    assert actual == {
        path: value for path, value in old_inventory.items() if path.startswith("shared/")
    }
    assert shutil.disk_usage(root.parent).free >= RESERVE
    existing = root.exists()
    if not existing:
        root.mkdir(mode=0o700)
    else:
        assert {path.name for path in root.iterdir()} == set(previous.ROLES)
    for role in previous.ROLES:
        old = previous.MOUNT / A2A_CASE / role
        new = root / role
        if not existing:
            new.mkdir(mode=0o755)
        for filename in ("binding.json", "fixture.tar.gz"):
            assert file_digest(old / filename) == old_inventory[f"{A2A_CASE}/{role}/{filename}"]
        assert file_digest(old / "fixture.tar.gz") == diagnostics[role]["fixture_sha256"]
        if not existing:
            shutil.copyfile(old / "fixture.tar.gz", new / "fixture.tar.gz")
        bound = get(old / "binding.json")
        prior, corrected = (
            diagnostics[role][key] for key in ("published_identity", "actual_source_identity")
        )
        assert bound["outcomes"][prior] == diagnostics[role]["expected_status"]
        assert corrected not in bound["outcomes"]
        bound["outcomes"] = {
            corrected if key == prior else key: value for key, value in bound["outcomes"].items()
        }
        assert len(bound["outcomes"]) == 81 and bound["archive_sha256"] == file_digest(
            new / "fixture.tar.gz"
        )
        if existing:
            assert {p.name for p in new.iterdir()} == {"binding.json", "fixture.tar.gz"}
            assert get(new / "binding.json") == bound
        else:
            put(new / "binding.json", bound)
            freeze(new)
    return {
        "case_id": A2A_CASE,
        "roles": list(previous.ROLES),
        "identity_count": 81,
        "settled_prior_operations": 5,
        "independent_pairs_already_verified": 2,
        "prior_approved_review": results["review_sha256"],
        "changed_input": "One selector in each role. Fixture, reference patch and all assertions are byte-identical.",
        "sha256_by_staged_root": {
            str(path): content_digest(tree(path))
            for path in [shared, *(root / role for role in previous.ROLES)]
        },
    }
