"""Prepare an exact local repeat for the pinned FuseSoC snapshot."""

import argparse
import asyncio
import json
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from check_linux_install import DOCKER, HERE, IMAGE, ROOT, SOCKET, WORK, Scope, docker, get, put
from repository_offline_pair_batch import context
from run_fusesoc_reference import MOUNT as EARLIER_MOUNT
from stage_repository_transport import digest, read

import aeep
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "aeep-c13-fusesoc-scm-20261116"
MOUNT = Path("/private/tmp") / NAME / "protected"
TARGET = WORK / "fusesoc-scm-metadata"
REVIEW = TARGET / "operation-review.json"
OUTPUT = TARGET / "execution"
FROZEN = WORK / "transport-grader-current-source"
SOURCE = "9710ea4f129d21affc0dcbe85e2d0bc432a41e5ec9ee8899b68df8a834959786"
ROLES = ("reference", "original")
DISK_FLOOR = 50 * 1024**3
TIME_LIMIT = 50
REVISION = "d2e6e720222f57cb66d6c303a326d336c582aade"
TAG = "2.4.5"
TAG_SHA = "a8730bd4d7b4d344909af2b7f00b1c6a66be211f"
NEXT_TAG_SHA = "5a32d93966be9a6daa4612509c6aba0173ccae7e"
SCM_NAME = "setuptools_scm-8.3.1-py3-none-any.whl"
SCM_SHA = "332ca0d43791b818b841213e76b1971b7711a960761c5bea5fc5cdb5196fbce3"
SETUPTOOLS_NAME = "setuptools-75.8.2-py3-none-any.whl"
SETUPTOOLS_SHA = "558e47c15f1811c1fa7adbd0096669bf76c1d3f433f58324df69f3f5ecac4e8f"
METADATA_PINS = {
    "commit.json": "df75a068b0d106cf49483f392afe1e571e1f9b85da556512b7c646483f7f20cf",
    "from-tag.json": "609c28e18f0fc21efb82ef7091220479e1127d64c9d8cab0393dc30175a658e9",
    "to-tag.json": "d1905a024dac8afe49680c658ca37d87a5133a2d6c68eafa3ec43209c15226c2",
    "tags.json": "d063acde1e3096ed89524759b295cf94e90ec41ab6cb4521b689b0ce4898e297",
}
SCM_PROGRAM = HERE / "fusesoc_build_metadata.py"
EARLIER_RESULT = HERE / "fusesoc-scratch-correction-result.json"


def verified_scope():
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
        or shutil.disk_usage(MOUNT.parents[1]).free < DISK_FLOOR
    ):
        raise ValueError("use the frozen coordinator source and retain the host reserve")
    prior = get(EARLIER_RESULT)
    review = json.loads(read(WORK / "fusesoc-scratch-correction-review.json", prior["review_sha256"]))
    settled = WORK / prior["execution_record_root"].split("/")[-1]
    read(settled / "ledger.json", prior["ledger_sha256"])
    read(settled / "reference-receipt.json", prior["receipt_sha256"])
    if (
        prior["roles"]["reference"]["observation"]["failure_categories"] != {
            "ModuleNotFoundError": 15
        }
        or prior["original_source_dispatched"] is not False
        or review["base_commit"] != REVISION
    ):
        raise ValueError("this continuation only covers the recorded import failure")
    return prior, review


def git_binding(metadata):
    commit, before, after, tags = (metadata[name] for name in METADATA_PINS)
    tag_map = {row["name"]: row["commit"]["sha"] for row in tags}
    if (
        tag_map.get(TAG) != TAG_SHA
        or tag_map.get("2.4.6") != NEXT_TAG_SHA
        or len(tags) != 38
        or len(tag_map) != len(tags)
        or commit["sha"] != REVISION
        or before["commits"][-1]["sha"] != REVISION
        or after["commits"][-1]["sha"] != NEXT_TAG_SHA
    ):
        raise ValueError("published source or tag inventory differs")
    for interval, base, count in ((before, TAG_SHA, 49), (after, REVISION, 6)):
        distinct = {item["sha"] for item in interval["commits"]}
        if (
            interval["merge_base_commit"]["sha"] != base
            or interval["base_commit"]["sha"] != base
            or interval["status"] != "ahead"
            or interval["behind_by"] != 0
            or interval["ahead_by"] != count
            or interval["total_commits"] != count
            or len(distinct) != count
            or len(interval["commits"]) != count
        ):
            raise ValueError("GitHub comparison did not preserve the complete ancestry interval")
    if set(tag_map.values()) & {item["sha"] for item in before["commits"]}:
        raise ValueError("versioned tag inside the supposed untagged interval")
    return {
        "tag": TAG,
        "tag_commit": TAG_SHA,
        "revision": REVISION,
        "tree": commit["commit"]["tree"]["sha"],
        "distance": 49,
        "expected_version": "2.4.6.dev49+g" + REVISION,
        "node_format": "full_commit",
    }


def metadata_binding():
    metadata = {name: json.loads(read(TARGET / name, pin)) for name, pin in METADATA_PINS.items()}
    return git_binding(metadata)


def projected_guest(guest):
    code = guest.decode()
    helper = SCM_PROGRAM.read_text()
    hook = "        os.chdir(target)"
    output = '        "role": phase, "exit_code": code, "exact_test_identities": exact,'
    if code.count(hook) != 1 or code.count(output) != 1:
        raise ValueError("first-party protected observer insertion points changed")
    code = code.replace(
        hook,
        """        binding = json.loads((ROOT / "scm-binding.json").read_bytes())
        sys.path[:0] = [str(packages / filename) for filename in (""" + repr(SCM_NAME)
        + ", " + repr(SETUPTOOLS_NAME) + """)]
        version = generate_version_file(target, packages, binding)
        version_pin = hashlib.sha256((target / "fusesoc/version.py").read_bytes()).hexdigest()
""" + hook,
    ).replace(output, output + '\n        "generated_version": version, "version_sha256": version_pin,')
    code = helper + "\n\n" + code
    compile(code, "<contained FuseSoC observer>", "exec")
    return code.encode()


def staging_inventory():
    if any(path.is_symlink() for path in MOUNT.rglob("*")):
        raise ValueError("private grading mount contains a symlink")
    return {
        path.relative_to(MOUNT).as_posix(): file_digest(path)
        for path in sorted(MOUNT.rglob("*"))
        if path.is_file()
    }


def stage(binding, earlier):
    wheel = TARGET / SCM_NAME
    read(wheel, SCM_SHA)
    setuptools = ROOT / ".aeep/repository-test-root-wheels-20261027" / SETUPTOOLS_NAME
    read(setuptools, SETUPTOOLS_SHA)
    with ZipFile(wheel) as data:
        package = "setuptools_scm-8.3.1.dist-info"
        notice = data.read(f"{package}/licenses/LICENSE")
        if b"Permission is hereby granted" not in notice or b"Version: 8.3.1\n" not in data.read(
            f"{package}/METADATA"
        ):
            raise ValueError("publisher metadata or license notice differs")
    mount_data = {name: read(EARLIER_MOUNT / name, pin) for name, pin in earlier["files"].items()}
    pins = json.loads(mount_data["protected-inputs.json"])
    if pins["source_revision"] != REVISION:
        raise ValueError("source commit and retained grading fixture differ")
    for asset in pins["assets"].values():
        files = archive_files(mount_data[asset["file"]])
        if digest(mount_data[asset["file"]]) != asset["sha256"] or "fusesoc/version.py" in files:
            raise ValueError("protected source asset or its missing-file diagnosis drifted")
    mount_data["guest.py"] = projected_guest(mount_data["guest.py"])
    mount_data["scm-binding.json"] = (json.dumps(binding, indent=2) + "\n").encode()
    for package in (wheel, setuptools):
        mount_data["support/" + package.name] = package.read_bytes()
    expected = {name: digest(body) for name, body in mount_data.items()}
    if MOUNT.exists():
        if staging_inventory() != expected:
            raise ValueError("previously staged files differ")
        return digest(notice)
    MOUNT.parent.mkdir(mode=0o700)
    MOUNT.mkdir(mode=0o755)
    for name, content in mount_data.items():
        path = MOUNT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    for path in MOUNT.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    MOUNT.chmod(0o555)
    files = staging_inventory()
    if files != expected:
        raise ValueError("the new mount changed an earlier input")
    return digest(notice)


def specs():
    sandbox = AssessmentEnvironment(
        environment_id=NAME, kind="container", container_image=IMAGE,
        container_runtime=DOCKER, container_socket=SOCKET, network=False,
        identity={"source": SOURCE, "mount": content_digest(staging_inventory())},
        read_only_roots=[str(MOUNT)], memory_mb=512, process_limit=96, container_tmpfs_mb=32,
    )
    return sandbox, {
        role: ExecutorSpec(
            id="toolkit.fusesoc-reference", kind="command",
            capability="toolkit.upstream-engineering@1",
            description="Pinned FuseSoC test collection after SCM metadata generation",
            config={
                "argv": ["python3", "-I", "-B", str(MOUNT / "guest.py"), role, str(FROZEN / "src")],
                "argv_literal": True, "timeout_seconds": 40, "max_output_bytes": 16384,
                "output": {"type": "json"},
            },
        )
        for role in ROLES
    }


def reviewed_launches(sandbox, specs_by_role):
    executor = ContainerExecutor(sandbox)
    launches = {}
    for role in ROLES:
        spec = specs_by_role[role]
        identity = NAME + ":" + role
        trial = context(spec, identity, {})
        argv, owned = executor.command(trial)
        if (
            {arg for arg in argv if arg.startswith("type=bind,")}
            != {f"type=bind,src={p},dst={p},readonly" for p in (MOUNT, FROZEN / "src")}
            or argv[argv.index("--network") + 1] != "none"
            or argv[argv.index("--user") + 1] != "65534:65534"
            or not {"--read-only", "--cap-drop=ALL", "--pull=never"} <= set(argv)
        ):
            raise ValueError("grading command differs from the protected boundary")
        launches[role] = {
            "argv_sha256": content_digest({"argv": argv}), "owned_container": owned,
        }
    return launches


def review_fields():
    prior, preceding = verified_scope()
    image = json.loads(docker("image", "inspect", "--format", "{{json .}}", IMAGE))
    config = image["Config"]
    if (
        image["Id"] != IMAGE or image["RootFS"]["Layers"] != preceding["layers"]
        or (image["Os"], image["Architecture"]) != ("linux", "arm64")
        or config.get("Volumes") or config.get("Healthcheck")
    ):
        raise ValueError("retained grader image changed")
    sandbox, role_specs = specs()
    return {
        "schema_version": "aeep.c13.fusesoc-build-metadata-review.v1",
        "source": SOURCE,
        "source_metadata": metadata_binding(),
        "public_metadata_sha256": METADATA_PINS,
        "driver_sha256": file_digest(Path(__file__)),
        "helper_sha256": file_digest(SCM_PROGRAM),
        "context_helper_sha256": file_digest(HERE / "repository_offline_pair_batch.py"),
        "docker_helper_sha256": file_digest(HERE / "check_linux_install.py"),
        "docker_sha256": file_digest(Path(DOCKER)),
        "prior_reference_sha256": file_digest(EARLIER_RESULT),
        "prior_review_sha256": prior["review_sha256"],
        "prior_charges_preserved": True,
        "existing_image": IMAGE,
        "layers": preceding["layers"],
        "files": staging_inventory(),
        "sandbox": sandbox.model_dump(mode="json"),
        "launches": reviewed_launches(sandbox, role_specs),
        "wheels": {SCM_NAME: SCM_SHA, SETUPTOOLS_NAME: SETUPTOOLS_SHA},
        "scope": "One reference repeat, then the unstarted original only after the reference passes.",
        "maximum_operations": 2,
        "maximum_reserved_seconds": 2 * TIME_LIMIT,
        "models": 0, "cash_usd": 0, "retries": 0,
        "downloads": 0, "builds": 0, "installs": 0, "provider_disclosure": False,
    }


def prepare():
    if REVIEW.exists():
        raise ValueError("review already exists")
    _, prior = verified_scope()
    stage(metadata_binding(), prior)
    review = review_fields()
    put(REVIEW, {**review, "expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    print(file_digest(REVIEW))


def exact_preflight(exact, approval, out):
    if out.exists() or file_digest(REVIEW) != exact:
        raise ValueError("terminal or interrupted attempt exists, or review changed")
    if get(approval) != {"approved": True, "review_sha256": exact}:
        raise ValueError("operator approval does not bind this review")
    approved = get(REVIEW)
    expiry = datetime.fromisoformat(approved["expires_at"])
    live = review_fields()
    if approved != {**live, "expires_at": approved["expires_at"]} or expiry <= utc_now():
        raise ValueError("operation review drifted or expired")
    return approved, expiry


def interpret_reply(observed, role, expected_version, reference_version_pin):
    version_pin = observed.get("version_sha256")
    matched = (
        observed.get("role") == role and observed.get("expected_outcome") is True
        and observed.get("exact_test_identities") is True
        and observed.get("collected") == 15 and observed.get("setup_and_teardown_errors") == 0
        and observed.get("generated_version") == expected_version
        and isinstance(version_pin, str) and bool(re.fullmatch("[0-9a-f]{64}", version_pin))
        and (role == "reference" or version_pin == reference_version_pin)
        and observed.get("exit_code") == int(role == "original")
        and observed.get("passed") == (15 if role == "reference" else 14)
        and observed.get("failed") == int(role == "original")
    )
    categories = observed.get("failure_categories")
    return {
        "expected_outcome": matched,
        "version_sha256": version_pin if matched else None,
        **{
            key: observed[key]
            for key in ("collected", "exit_code", "passed", "failed", "setup_and_teardown_errors")
            if type(observed.get(key)) is int and 0 <= observed[key] <= 100
        },
        "failure_categories": {
            key: value for key, value in categories.items()
            if key in {"ModuleNotFoundError", "ImportError", "AssertionError", "PermissionError"}
            and type(value) is int and 0 <= value <= 15
        } if isinstance(categories, dict) else {},
    }


async def run(exact):
    review, expiry = exact_preflight(exact, TARGET / "approval.json", OUTPUT)
    sandbox, role_specs = specs()
    executor = ContainerExecutor(sandbox)
    definition = Scope(review_sha256=exact)
    fingerprint = content_digest(definition)
    request = RecipeMaterializationRequest(
        plan_id=NAME, authorization_id=NAME, subject_digest=fingerprint,
        recipe_digest=fingerprint, mapping_digest=fingerprint, environment_digest=fingerprint,
        definition_digests=[fingerprint], seed=0,
    )
    authority = AssessmentAuthorization(
        authorization_id=NAME, subject_digests=[fingerprint], recipe_digests=[fingerprint],
        environment_digests=[fingerprint], allowed_destinations=["local"], expires_at=expiry,
        limits=AssessmentLimits(max_operations=2, max_elapsed_seconds=2 * TIME_LIMIT),
        remote_disclosure=False,
    )
    OUTPUT.mkdir(mode=0o700)
    results = {}
    with ReceiptStore(OUTPUT / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_fusesoc_build_metadata_scope", fingerprint, definition)
        repo.approve_bundle(authority, {fingerprint: definition.model_dump(mode="json")})
        try:
            for role, spec in role_specs.items():
                identity = NAME + ":" + role
                trial = context(spec, identity, {})
                argv, owned = executor.command(trial)
                if (
                    review_fields() != {key: value for key, value in review.items() if key != "expires_at"}
                    or review["launches"][role] != {
                        "argv_sha256": content_digest({"argv": argv}), "owned_container": owned,
                    }
                    or docker("ps", "-aq", "--filter", f"name=^/{owned}$")
                ):
                    raise ValueError("frozen operation scope or owned-container availability changed")
                repo.reserve(
                    request, identity, AssessmentLimits(max_operations=1, max_elapsed_seconds=TIME_LIMIT),
                    stage="fusesoc_protected_reference", require_settled_plan=True,
                )
                started, before = utc_now(), time.monotonic()
                raw = await executor.execute(trial)
                elapsed = time.monotonic() - before
                if docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
                    raise RuntimeError("owned container absence uncertain; retain unsettled charge")
                observed = raw.output if raw.status.value == "success" and isinstance(raw.output, dict) else {}
                details = interpret_reply(
                    observed, role, review["source_metadata"]["expected_version"],
                    results.get("reference", {}).get("version_sha256"),
                )
                success = details["expected_outcome"]
                receipt = ExecutionReceipt(
                    decision_id=identity, action_id=identity, capability=spec.capability, executor_id=spec.id,
                    executor_kind=spec.kind, status="success" if success else "failed",
                    execution_success=success, started_at=started, ended_at=utc_now(),
                    estimated=trial.estimate, actual_resources=raw.resources,
                    error_type=None if success else raw.error_type or "OBSERVATION_MISMATCH",
                    metadata={"review_sha256": exact, "container_absent": True, "observation": details},
                )
                store.save_receipt(receipt)
                repo.finish_operation(identity, elapsed_seconds=elapsed, resources=raw.resources)
                results[role] = {"receipt_id": receipt.receipt_id, **details}
                put(OUTPUT / (role + "-receipt.json"), receipt.model_dump(mode="json"))
                if not success:
                    break
        finally:
            await executor.close()
            put(OUTPUT / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    passed = tuple(results) == ROLES and all(row["expected_outcome"] for row in results.values())
    put(OUTPUT / "result.json", {
        "passed": passed, "review_sha256": exact, "roles": results, "formal_stage_assigned": False,
    })
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        asyncio.run(run(args.exact_review))
