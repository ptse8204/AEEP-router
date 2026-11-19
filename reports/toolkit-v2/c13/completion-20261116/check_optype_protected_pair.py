"""Stage and run the verified Optype reference and original protected checks."""

import argparse
import asyncio
import base64
import io
import json
import tomllib
from collections import Counter
from datetime import timedelta
from importlib.metadata import distributions
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import repository_offline_pair_batch as runner
from acquire_full_rebench_leads import TARGET, ref
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_advanced_alchemy_pair import FROZEN, SOURCE, verify_source
from screen_candidate_patches import assess, load_reviewed_helpers, stage_file
from stage_repository_transport import ROOT, bind_row, digest, encode, read, write

from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import Wheel, check_wheel

CASE = "jorenham__optype-29"
NAME = "c13-optype-protected-pair-20261119"
DIRECTORY = TARGET / "optype-ordinary"
BASE_REVIEW, BASE_PROBE = runner.review_fields, runner.verify_probe
VERSION = "0.2.2"


def establish_checkout_distribution(project, notices):
    if (
        project["name"] != "optype"
        or project["version"] != VERSION
        or project["dependencies"] != {"python": "^3.12"}
        or len(notices) != 1
    ):
        raise ValueError("publisher metadata or active dependency closure changed")
    stem = f"optype-{VERSION}.dist-info"
    ((license_name, content),) = notices.items()
    entries = {
        f"{stem}/METADATA": (
            f"Metadata-Version: 2.4\nName: optype\nVersion: {VERSION}\n"
            f"Requires-Python: >=3.12,<4.0\nLicense-Expression: BSD-3-Clause\n"
            f"License-File: {license_name}\n\n"
        ).encode(),
        f"{stem}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: AEEP protected checkout metadata\n"
            b"Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        f"{stem}/licenses/{license_name}": content,
    }
    records = []
    for name, body in sorted(entries.items()):
        token = base64.urlsafe_b64encode(bytes.fromhex(digest(body))).rstrip(b"=").decode()
        records.append(f"{name},sha256={token},{len(body)}\n")
    entries[f"{stem}/RECORD"] = ("".join(records) + f"{stem}/RECORD,,\n").encode()
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as wheel:
        for name, data in sorted(entries.items()):
            wheel.writestr(ZipInfo(name), data)
    return buffer.getvalue()


def stage():
    archive = json.loads((TARGET / "archives-result.json").read_bytes())[CASE]
    source_ref = archive["archive"]
    path = ROOT / source_ref["path"]
    read(path, source_ref["sha256"])
    lead = archive | {
        "instance_id": CASE,
        "base_commit": archive["source_revision"],
        "source_bindings": [
            {
                "archive": source_ref["path"],
                "sha256": source_ref["sha256"],
                "license_notices": archive["license_notices"],
            }
        ],
    }
    prepared, assets = assess(
        lead, load_reviewed_helpers(), reviewed_frozen_metadata={"pyproject.toml"}
    )
    # The declared metadata amendment must stay entirely inside Ruff configuration.
    import tarfile

    with tarfile.open(path, "r:gz") as source:
        (member,) = [
            item
            for item in source
            if item.isfile() and item.name.split("/", 1)[-1] == "pyproject.toml"
        ]
        original = tomllib.loads(source.extractfile(member).read().decode())
    public = archive_files(assets["source.tar.gz"], large=True)
    restored = tomllib.loads(public["pyproject.toml"].decode())
    if original["tool"].pop("ruff") == restored["tool"].pop("ruff") or original != restored:
        raise ValueError("pyproject differences must be confined to the reviewed Ruff settings")
    notices = {item["file"]: public[item["file"]] for item in archive["license_notices"]}
    for item in archive["license_notices"]:
        if digest(notices[item["file"]]) != item["sha256"]:
            raise ValueError("retained publisher license differs")
    metadata = establish_checkout_distribution(restored["tool"]["poetry"], notices)
    wheel_path = DIRECTORY / f"optype-{VERSION}-py3-none-any.whl"
    write(wheel_path, metadata)
    check_wheel(
        wheel_path,
        Wheel(
            extension_id="optype",
            name="optype",
            filename=wheel_path.name,
            version=VERSION,
            sha256=digest(metadata),
        ),
    )
    (dist,) = distributions(path=[str(wheel_path)])
    if dist.metadata["Name"] != "optype" or dist.version != VERSION:
        raise ValueError("version lookup would not match the reviewed checkout")
    prepared["case_id"] = CASE
    assets_root = DIRECTORY / "staged"
    (assets_root / CASE).mkdir(parents=True, mode=0o700)
    prepared["assets"] = [
        stage_file(assets_root / CASE, name, data) for name, data in assets.items()
    ]
    transport = DIRECTORY / "transport"
    row = bind_row(prepared, lead, transport, assets_root, source_ref["path"])
    write(transport / "private-index.json", encode([row]))
    write(
        DIRECTORY / "stage-result.json",
        encode(
            {
                "index": ref(transport / "private-index.json"),
                "distribution": ref(wheel_path),
                "publisher_archive": source_ref,
                "reference_changed_paths": row["input"]["editable_paths"],
                "license_notices": archive["license_notices"],
                "required_identities": 416,
                "runtime": "Retained CPython 3.13, publisher Python constraint also admits 3.13. Observer disables exit-first to record original-case preservations.",
                "frozen_ruff_metadata": prepared["frozen_metadata"],
                "upstream_tests_executed": 0,
            }
        ),
    )


def configure(observations):
    verify_source()
    staged = json.loads((DIRECTORY / "stage-result.json").read_bytes())
    index = ROOT / staged["index"]["path"]
    (row,) = json.loads(read(index, staged["index"]["sha256"]))
    baseline, wheels = wheel_probe_assets()
    dist = staged["distribution"]
    wheels.append(runner.asset(ROOT / dist["path"], dist["sha256"]))
    task, truth, reference, original, _ = bind(row, index.parent, wheels)
    if (len(truth.fail_to_pass), len(truth.pass_to_pass)) != (12, 404):
        raise ValueError("required issue or preservation identities drifted")
    public = archive_files(truth.source.read(), large=True)
    settings = tomllib.loads(public["pyproject.toml"].decode())["tool"]["pytest"]["ini_options"]
    flags = settings["addopts"]
    if flags.count("--exitfirst") != 1 or settings["xfail_strict"] is not True:
        raise ValueError("reviewed pytest collection settings differ")
    other_flags = " ".join(flag for flag in flags if flag != "--exitfirst")
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (
        (runtime / "repository_suite_native_program.py")
        .read_text()
        .replace(
            "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
            repr((runtime / "repository_suite_native_capture.py").read_text()),
        )
    )
    anchor = "'-p', 'no:cacheprovider', *request['test_paths']"
    if program.count(anchor) != 1:
        raise ValueError("ordinary observer options changed")
    program = program.replace(
        anchor, anchor.replace("*request", '"-o", ' + repr("addopts=" + other_flags) + ", *request")
    )
    compile(program, "<Optype ordinary grader>", "exec")
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Protected Optype protocol tests",
        config={
            "argv": ["python3", "-B", "-c", program],
            "argv_literal": True,
            "stdin_json": True,
            "output": {"type": "json"},
            "timeout_seconds": 32,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
        },
    )
    environment = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        network=False,
        container_image=runner.CARRIER,
        identity={"source": SOURCE, "staging": ref(DIRECTORY / "stage-result.json")["sha256"]},
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )
    case = {
        "case_id": CASE,
        "source_revision": row["source_revision"],
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [],
    }

    def observe(reply, payload, expected, code):
        accepted = BASE_PROBE(reply, payload, expected, code)
        note = {
            "role": "original" if code else "reference",
            "contract_matched": accepted,
            "archive_sha256": payload["archive_sha256"],
        }
        if isinstance(reply, dict) and isinstance(reply.get("statuses"), dict):
            statuses = reply["statuses"]
            note.update(
                pytest_exit=reply.get("exit_code"),
                required_status_counts=dict(Counter(statuses.get(k, "MISSING") for k in expected)),
                differences=[
                    {"test": k, "observed": statuses.get(k, "MISSING"), "expected": v}
                    for k, v in expected.items()
                    if statuses.get(k, "MISSING") != v
                ],
            )
        observations.append(note)
        return accepted

    async def review_fields():
        fields, *_ = await BASE_REVIEW()
        if [call["required_tests"] for call in fields["launches"]] != [416, 416]:
            raise ValueError("the observer did not bind the full protected requirement")
        return (
            fields
            | {
                "schema_version": "aeep.c13.optype-protected-pair.v1",
                "driver": ref(Path(__file__)),
                "staging": ref(DIRECTORY / "stage-result.json"),
                "base_test_wheels_sha256": baseline,
                "upstream_test_adaptation": "Disable exit-first only. The run preserves all required test identities.",
                "no_automatic_retries": True,
                "comparisons_paused": True,
                "waza_excluded": True,
            },
            spec,
            environment,
            [case],
        )

    runner.NAME, runner.FROZEN, runner.MAX_CALLS = NAME, FROZEN, 2
    runner.REVIEW, runner.APPROVAL = (
        DIRECTORY / "operation-review.json",
        DIRECTORY / "approval.json",
    )
    runner.RUN = DIRECTORY / "execution"
    runner.definitions = lambda: (spec, environment, [case])
    runner.review_fields, runner.verify_probe = review_fields, observe


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--stage", action="store_true")
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--exact-review")
    args = parser.parse_args()
    if args.stage:
        stage()
        return
    observed = []
    configure(observed)
    if args.prepare:
        scope, *_ = await runner.review_fields()
        runner.put(
            runner.REVIEW, scope | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()}
        )
        print(runner.file_digest(runner.REVIEW))
    else:
        try:
            passed = await runner.run(args.exact_review)
        finally:
            if observed and runner.RUN.exists():
                runner.put(runner.RUN / "required-test-observations.json", observed)
        raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
