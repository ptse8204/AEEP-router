"""Prepare the Arta protected callback with pinned private runtime inputs."""

import asyncio
import base64
import hashlib
import io
import json
import tomllib
from importlib.metadata import distributions
from zipfile import ZipFile, ZipInfo

from audit_staged_repository_graders import bind, wheel_probe_assets
from stage_repository_transport import HERE, ROOT, WORK, digest, read

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import archive_files, grade_suite_output
from aeep_toolkit.install_runtime import Wheel, check_wheel

CASE = "MAIF__arta-50-aeep-contract-audit"
ASSETS = WORK / "arta-runtime-inputs-20261117"
ARTIFACT = ASSETS / "omegaconf-2.4.0-py3-none-any.whl"
IMAGE = "sha256:4474cf22f867c681aa6120ce2f98d809413f89755cf11a445444b1b993754ea1"
OMEGACONF = "f141a664c777582405e3cc6e0545ecc79429e79f844995b1a6e71c35946a025c"
SOURCE_INDEX = HERE / "ancillary-contract-audits.json"
VERSION = "0.10.3"


def pin(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes())}


def metadata_wheel(project, notices):
    """Use the publisher's version metadata while importing the checkout itself."""
    if project["name"] != "arta" or project["version"] != VERSION:
        raise ValueError("Arta's declared metadata changed")
    stem = f"arta-{VERSION}.dist-info"
    raw = [
        "Metadata-Version: 2.4", "Name: arta", f"Version: {VERSION}",
        f"Requires-Python: {project['requires-python']}", "License-Expression: Apache-2.0",
        *(f"Requires-Dist: {item}" for item in project["dependencies"]),
        *(f"License-File: {name}" for name in sorted(notices)),
    ]
    entries = {
        f"{stem}/METADATA": ("\n".join(raw) + "\n\n").encode(),
        f"{stem}/WHEEL": b"Wheel-Version: 1.0\nGenerator: AEEP protected fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        **{f"{stem}/licenses/{name}": body for name, body in notices.items()},
    }
    record = []
    for name, body in sorted(entries.items()):
        token = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
        record.append(f"{name},sha256={token},{len(body)}\n")
    entries[f"{stem}/RECORD"] = ("".join(record) + f"{stem}/RECORD,,\n").encode()
    archive = io.BytesIO()
    with ZipFile(archive, "w") as wheel:
        for name, body in sorted(entries.items()):
            wheel.writestr(ZipInfo(name), body)
    return archive.getvalue()


async def stage():
    intake = json.loads(SOURCE_INDEX.read_bytes())
    index_path = ROOT / intake["private_index"]
    row = next(r for r in json.loads(read(index_path, intake["private_index_sha256"]))
               if r["input"]["task_id"] == CASE)
    core_ref, wheels = wheel_probe_assets()
    task, truth, reference, original, _ = bind(row, index_path.parent, wheels)
    public = archive_files(truth.source.read(), large=True)
    project = tomllib.loads(public["pyproject.toml"].decode())["project"]
    notices = {}
    for entry in row["license_notices"]:
        name = entry["file"]
        original_notice = public[name]
        if digest(original_notice) != entry["sha256"]:
            raise ValueError("retained publisher license notice changed")
        notices[name] = original_notice
    if not {"LICENSE", "NOTICE"} <= notices.keys():
        raise ValueError("required publisher attribution missing")
    acquired = ASSETS / "acquisition.json"
    acquisition = json.loads(acquired.read_bytes())
    if acquisition["sha256"] != OMEGACONF or acquisition["bytes"] != len(read(ARTIFACT, OMEGACONF)):
        raise ValueError("exact dependency acquisition changed")
    check_wheel(ARTIFACT, Wheel(
        extension_id="omegaconf", filename=ARTIFACT.name, name="omegaconf", version="2.4.0", sha256=OMEGACONF,
    ))
    with ZipFile(ARTIFACT) as wheel:
        if any(digest(wheel.read(name)) != sha for name, sha in acquisition["licenses"].items()):
            raise ValueError("upstream dependency notice changed")
    carrier_file = ASSETS / "carrier-distributions.json"
    carrier = json.loads(carrier_file.read_bytes())
    if (carrier["image"] != IMAGE or carrier["declared_platform"] != "linux/arm64"
            or {k: v["version"] for k, v in carrier["installed_metadata"].items()}
            != {"pydantic": "2.13.5", "pydantic-core": "2.46.5", "pyyaml": "6.0.3"}):
        raise ValueError("retained dependency inventory changed")
    if b'version("arta")' not in public["src/arta/__init__.py"]:
        raise ValueError("source no longer has the reviewed distribution lookup")
    metadata_path = ASSETS / f"arta-{VERSION}-py3-none-any.whl"
    metadata = metadata_wheel(project, notices)
    if not metadata_path.exists():
        with metadata_path.open("xb") as out:
            out.write(metadata)
    if metadata_path.read_bytes() != metadata:
        raise ValueError("local Arta distribution metadata changed")
    check_wheel(metadata_path, Wheel(
        extension_id="arta", filename=metadata_path.name, name="arta", version=VERSION, sha256=digest(metadata),
    ))
    with ZipFile(metadata_path) as wheel:
        if not all(name.startswith(f"arta-{VERSION}.dist-info/") for name in wheel.namelist()):
            raise ValueError("metadata projection contains importable code")
    only, = distributions(path=[str(metadata_path)])
    if (only.metadata["Name"], only.version) != ("arta", VERSION):
        raise ValueError("Arta's version lookup cannot resolve its source package metadata")
    wheel_inputs = [*wheels, *[
        {"path": str(path), "size_bytes": path.stat().st_size, "sha256": pin(path)["sha256"]}
        for path in (ARTIFACT, metadata_path)
    ]]
    prepared_truth = type(truth).model_validate(truth.model_dump(mode="json") | {"wheels": wheel_inputs})
    required = prepared_truth.pass_to_pass
    oracle = index_path.parent / "protected" / CASE / "required.json"
    declared = json.loads(read(oracle, row["protected_assets"]["required.json"]["sha256"]))
    original_failures = set(declared["published_fail_to_pass"]) | {row["protected_guard"]}
    if len(required) != 17 or len(original_failures) != 3:
        raise ValueError("original assertion or preservation scope differs")
    staged = {}
    for role, submission in (("reference", reference), ("original", original)):
        async def substitute(payload, role=role):
            expected_archive = row["reference_archive_sha256" if role == "reference" else "fault_archive_sha256"]
            if (payload["archive_sha256"] != expected_archive or payload["source_modules"] != ["arta"]
                    or len(payload["wheels"]) != 6):
                raise ValueError("ordinary callback changed protected bytes or import ownership")
            staged[role] = {
                "payload_sha256": content_digest(payload),
                "archive_sha256": expected_archive,
                "required_tests": len(required),
            }
            statuses = dict.fromkeys(required, "PASSED")
            if role == "original":
                statuses.update(dict.fromkeys(original_failures, "FAILED"))
            return {**{key: payload[key] for key in ("archive_sha256", "python", "pytest")},
                    "exit_code": int(role == "original"), "statuses": statuses}

        grade = await grade_suite_output(
            task.model_dump(mode="json"), prepared_truth.model_dump(mode="json"), submission, substitute,
        )
        if grade.valid is not (role == "reference"):
            raise ValueError("substituted grade disagrees with the protected plan")
    return {
        "schema_version": "aeep.c13.arta-runtime-inputs.v1",
        "case": CASE, "revision": row["source_revision"],
        "source_index": pin(SOURCE_INDEX), "project_metadata_sha256": digest(public["pyproject.toml"]),
        "dependency_acquisition": acquisition, "dependency_acquisition_record": pin(acquired),
        "carrier_inventory": pin(carrier_file), "carrier": carrier,
        "metadata_only_distribution": pin(metadata_path), "metadata_only_version_lookup": VERSION,
        "base_test_wheel_review_sha256": core_ref, "portable_grader_inputs": wheel_inputs,
        "ordinary_callback_rehearsals": staged, "protected_source_archive_unchanged": True,
        "existing_upstream_identities": len(required) - 1, "authored_preservation_checks": 1,
        "upstream_tests_executed": 0, "package_code_imported": False, "new_model_turns": 0,
        "container_launches": 0, "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(stage()), indent=2, sort_keys=True, allow_nan=False))
