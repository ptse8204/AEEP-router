"""Verify Braindrop's protected search contract using the cached HTTPX closure."""

import argparse
import asyncio
import base64
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
import tomllib
from zipfile import ZipFile, ZipInfo

from packaging.requirements import Requirement

import check_expansion_contracts as contracts
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import archive_files
from aeep.models import utc_now
from audit_staged_repository_graders import bind, wheel_probe_assets

HERE, WORK, ROOT, runner = contracts.HERE, contracts.WORK, contracts.ROOT, contracts.runner
CASE = "davep__braindrop-96-aeep-contract-audit"
NAME = "c13-braindrop-protected-audit-20261118"
TARGET = WORK / NAME
WHEEL_LOCK = WORK / "a2a-offline-assets/wheel-lock.json"
LOCK_SHA256 = "bd1c43e3da9f9ddc65a11779c6ee6caf6ba620a6b6580b7202249b97ac5fbb8c"
CACHED = ("httpx", "httpcore", "h11", "anyio", "sniffio", "certifi", "idna")


def metadata_bytes(project, notice):
    stem = "braindrop-0.5.0.dist-info"
    requirements = "".join(f"Requires-Dist: {item}\n" for item in project["dependencies"])
    metadata = (
        "Metadata-Version: 2.4\nName: braindrop\nVersion: 0.5.0\n"
        f"Requires-Python: {project['requires-python']}\n"
        "License-File: LICENSE\n" + requirements + "\n"
    ).encode()
    payloads = {
        f"{stem}/METADATA": metadata,
        f"{stem}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{stem}/licenses/LICENSE": notice,
    }
    record = []
    for name, body in sorted(payloads.items()):
        checksum = base64.urlsafe_b64encode(bytes.fromhex(contracts.digest(body))).decode().rstrip("=")
        record.append(f"{name},sha256={checksum},{len(body)}\n")
    payloads[f"{stem}/RECORD"] = ("".join(record) + f"{stem}/RECORD,,\n").encode()
    output = BytesIO()
    with ZipFile(output, "w") as wheel:
        for name, body in sorted(payloads.items()):
            wheel.writestr(ZipInfo(name), body)
    return output.getvalue()


def inputs(*, stage):
    acquisition = contracts.pinned(HERE / "repository-expansion-acquisition-result.json")
    transport = WORK / "repository-expansion-acquisition" / "transport"
    row, = [item for item in json.loads(contracts.read(transport.parent / "index.json",
                                                       acquisition["candidate_index_sha256"]))
            if item["input"]["task_id"] == CASE]
    published, = [item for item in acquisition["candidates"] if item["case"] == CASE]
    _, baseline = wheel_probe_assets()
    task, truth, reference, original, _ = bind(row, transport, baseline)
    archive = archive_files(truth.source.read(), large=True)
    if (published["revision"] != row["source_revision"] or published["source_sha256"] != task.source_sha256
            or b'version("braindrop")' not in archive["src/braindrop/__init__.py"]
            or truth.test_paths != ["tests/test_aeep_preservation.py", "tests/unit/test_raindrop.py"]):
        raise ValueError("published source or protected test scope changed")
    project = tomllib.loads(archive["pyproject.toml"].decode())["project"]
    if project["name"] != "braindrop" or project["version"] != "0.5.0":
        raise ValueError("unexpected project distribution identity")
    notice_pin, = row["license_notices"]
    if (notice_pin["file"] != "LICENSE" or notice_pin != published["license_notices"][0]
            or contracts.digest(archive["LICENSE"]) != notice_pin["sha256"]):
        raise ValueError("published project notice changed")
    metadata = TARGET / "braindrop-0.5.0-py3-none-any.whl"
    packed = metadata_bytes(project, archive["LICENSE"])
    if stage and not metadata.exists():
        TARGET.mkdir(mode=0o700, parents=True, exist_ok=True)
        with metadata.open("xb") as output:
            output.write(packed)
        metadata.chmod(0o400)
    sha = contracts.digest(packed)
    contracts.read(metadata, sha)
    contracts.inspect_wheel(metadata, "braindrop", sha, "0.5.0")
    lock = json.loads(contracts.read(WHEEL_LOCK, LOCK_SHA256))["wheels"]
    pinned = {}
    for name in CACHED:
        wheel = lock[name]
        path = ROOT / wheel["path"]
        version = path.name.split("-")[1]
        pinned[name] = contracts.inspect_wheel(path, name, wheel["sha256"], version)
    expected_requirements = [
        Requirement(raw) for details in pinned.values() for raw in details["active_requires_dist"]
    ]
    expected_requirements += [Requirement(raw) for raw in project["dependencies"] if raw.startswith("httpx")]
    if any(req.url or req.extras or req.name not in pinned or pinned[req.name]["version"] not in req.specifier
           for req in expected_requirements):
        raise ValueError("cached HTTPX dependency closure does not match")
    wheels = [*baseline, runner.asset(metadata, sha)]
    wheels.extend(runner.asset(ROOT / item["path"], item["sha256"]) for item in pinned.values())
    truth = type(truth).model_validate(truth.model_dump(mode="json") | {"wheels": wheels})
    required = json.loads(contracts.read(transport / "protected" / CASE / "required.json",
                                         row["protected_assets"]["required.json"]["sha256"]))
    failures = {*required["published_fail_to_pass"], row["protected_guard"]}
    if len(truth.pass_to_pass) != 63 or not 1 < len(failures) < 63 or not failures <= set(truth.pass_to_pass):
        raise ValueError("protected preservation identities changed")
    case = {
        "case_id": CASE, "source_revision": row["source_revision"], "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"), "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"], "existing_image_dependencies": [],
    }
    return case, failures, published, pinned


def configure(*, stage=False):
    contracts.configure("opentelemetry")
    spec, template, _ = runner.definitions()
    env = template.model_copy(update={"environment_id": NAME})
    case, failures, published, pinned = inputs(stage=stage)
    runner.NAME, runner.REVIEW, runner.RUN = NAME, TARGET / "operation-review.json", TARGET / "execution"
    runner.APPROVAL = TARGET / "approval.json"

    def expected(oracle, role):
        statuses = dict.fromkeys(oracle["pass_to_pass"], "PASSED")
        if role == "original":
            statuses.update(dict.fromkeys(failures, "FAILED"))
        return statuses

    async def review_fields():
        base, _, _, _ = await contracts.BASE_REVIEW()
        roles = dict(zip(runner.ROLES, base["launches"], strict=True))
        for role, name in (("reference", "reference_transport"), ("original", "original_transport")):
            if (roles[role]["archive_sha256"] != published["protected_bindings"][name]["archive_sha256"]
                    or roles[role]["required_tests"] != 63):
                raise ValueError("protected payload or test inventory drift")
        return base | {
            "schema_version": "aeep.c13.braindrop-audit.v1",
            "wrapper_sha256": runner.file_digest(Path(__file__)),
            "upstream_notice": published["license_notices"],
            "publisher_acquisition_report_sha256": contracts.INPUTS[HERE / "repository-expansion-acquisition-result.json"],
            "cached_wheel_lock_sha256": LOCK_SHA256, "portable_inventory": pinned,
            "expected_original_failures": sorted(failures), "network": False, "installations": 0,
            "execution_scope": "Protected unit tests only. No TUI, Raindrop authentication or provider access.",
        }, spec, env, [case]

    runner.definitions, runner.expected_statuses, runner.review_fields = lambda: (spec, env, [case]), expected, review_fields


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    configure(stage=args.prepare)
    if args.exact_review:
        raise SystemExit(0 if await runner.run(args.exact_review) else 1)
    current, *_ = await runner.review_fields()
    if args.prepare:
        runner.put(runner.REVIEW, current | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    elif current != {key: value for key, value in runner.get(runner.REVIEW).items() if key != "expires_at"}:
        raise ValueError("the exact published scope changed")
    print(runner.file_digest(runner.REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
