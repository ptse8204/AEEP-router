"""Stage two upstream contract audits on retained, network-disabled graders."""
import argparse
import asyncio
from datetime import timedelta
from email.parser import BytesParser
import json
from pathlib import Path
import urllib.request
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

import aeep
import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_returnn_pair import FROZEN, PINNED_OBSERVER, SOURCE
from stage_repository_transport import HERE, ROOT, WORK, digest, read
from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.assessment.repository_suites import LARGE_PAYLOAD
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import Wheel, check_wheel, file_digest

WORKLOAD = HERE.parent / "repository-workload-batch-20261022"
INPUTS = {
    HERE / "opentelemetry-monorepo-preparation.json": "b198203c1559c0f90659f8f94d60b21d44b6fdce048bd50b3df943ea903fc594",
    HERE / "repository-expansion-acquisition-result.json": "1d44549f8e75bc24dbec542c3e8d1dfa5043edba28804dcd705319190b769124",
    HERE / "repository-expansion-runtime-triage.json": "c34b2d1b750ad863264964675e8da2d0f265adf20e5febe501ec6576b8d525a5",
    WORKLOAD / "build-result.json": "b172eb0ccf415a63ff8818ae0c4922e48fb0f17b3bb852b4e78e4c04e0c5743b",
    WORKLOAD / "runtime-install-review.json": "fa7712ce40011cd663768b777a8eafe01abf6d8a8ae5a465d535ae5f9c16330c",
    WORKLOAD / "approval-bundle.json": "38f87c22d21c564aa35dd9b9a05efec6657dd658bfddfe6ee3e74fcfbb35d3de",
}
OTEL = "open-telemetry__opentelemetry-python-4891-aeep-contract-audit"
GUARDIAN = "django-guardian__django-guardian-904-aeep-contract-audit"
PORTABLE = WORK / "c13-expansion-contracts-20261118" / "wheels"
BASE_REVIEW = runner.review_fields
GUARDIAN_PACKAGE = {
    "filename": "django_environ-0.12.0-py2.py3-none-any.whl", "version": "0.12.0",
    "hash": "sha256:92fb346a158abda07ffe6eb23135ce92843af06ecf8753f43adf9d2366dcc0ca",
    "size": 19957,
    "url": "https://files.pythonhosted.org/packages/83/b3/0a3bec4ecbfee960f39b1842c2f91e4754251e0a6ed443db9fe3f666ba8f/django_environ-0.12.0-py2.py3-none-any.whl",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def pinned(path):
    return json.loads(read(path, INPUTS[path]))


def portable_pins(key):
    if key == "django-guardian":
        return {"django-environ": GUARDIAN_PACKAGE}
    report = pinned(HERE / "opentelemetry-monorepo-preparation.json")
    return report["resolved_locked_wheel_candidates"]


def inspect_wheel(path, name, sha256, version):
    with ZipFile(path) as archive:
        metadata_path, = [item for item in archive.namelist() if item.endswith(".dist-info/METADATA")]
        raw = archive.read(metadata_path)
        metadata = BytesParser().parsebytes(raw)
        verified = Wheel(extension_id=name, name=metadata["Name"], version=version,
                         filename=path.name, sha256=sha256)
        if canonicalize_name(verified.name) != name:
            raise ValueError("wheel declared another project")
        check_wheel(path, verified)
        licenses = {
            item: digest(archive.read(item)) for item in archive.namelist()
            if item.startswith(metadata_path.removesuffix("METADATA")) and not item.endswith("/")
            and Path(item).name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
        }
        if not licenses:
            raise ValueError("wheel has no retained license notice")
        marker_environment = {"python_version": "3.13", "python_full_version": "3.13.15",
                              "sys_platform": "linux", "platform_system": "Linux",
                              "platform_machine": "aarch64", "extra": ""}
        if metadata["Requires-Python"] and "3.13.15" not in SpecifierSet(metadata["Requires-Python"]):
            raise ValueError("wheel does not admit the retained Python runtime")
        requirements = [Requirement(item) for item in metadata.get_all("Requires-Dist", [])]
        active = [str(req) for req in requirements if req.marker is None or req.marker.evaluate(marker_environment)]
    return {"name": name, "version": version, "filename": path.name,
            "metadata_sha256": digest(raw), "license_notice_digests": licenses, "active_requires_dist": active,
            "path": str(path.relative_to(ROOT)), "sha256": sha256, "size_bytes": path.stat().st_size}


def portable_assets(key, *, fetch=False):
    pins = portable_pins(key)
    if fetch:
        PORTABLE.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifacts = {}
    for project, item in sorted(pins.items()):
        retained = item.get("retained", [])
        path = ROOT / retained[0]["path"] if retained else PORTABLE / item["filename"]
        sha256 = item["hash"].removeprefix("sha256:")
        if fetch and not retained and not path.exists():
            url = item["url"]
            if not url.startswith("https://files.pythonhosted.org/packages/") or url.rsplit("/", 1)[-1] != path.name:
                raise ValueError("unexpected publisher URL")
            with urllib.request.build_opener(NoRedirect()).open(url, timeout=15) as response:
                body = response.read(item["size"] + 1)
            if len(body) != item["size"] or digest(body) != sha256:
                raise ValueError("publisher wheel size or checksum differs")
            with path.open("xb") as stream:
                stream.write(body)
            path.chmod(0o400)
        if path.is_symlink() or not path.is_file() or path.stat().st_size != item["size"] or file_digest(path) != sha256:
            raise ValueError("portable wheel absent or changed")
        artifacts[project] = inspect_wheel(path, project, sha256, item["version"])
    versions = {key: item["version"] for key, item in artifacts.items()}
    for item in artifacts.values():
        for raw in item["active_requires_dist"]:
            req = Requirement(raw)
            version = versions.get(canonicalize_name(req.name))
            if req.url or req.extras or version is None or version not in req.specifier:
                raise ValueError(f"unresolved portable dependency: {req}")
    return artifacts


def source_inputs(key):
    acquisition = pinned(HERE / "repository-expansion-acquisition-result.json")
    case = OTEL if key == "opentelemetry" else GUARDIAN
    publisher, = [row for row in acquisition["candidates"] if row["case"] == case]
    if key == "opentelemetry":
        report = pinned(HERE / "opentelemetry-monorepo-preparation.json")
        index = report["protected_rebind"]
        path = ROOT / index["path"]
        row, = json.loads(read(path, index["sha256"]))
        transport = path.parent
        carrier = "sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04"
        inherited, plugins = [], []
    else:
        parent = pinned(WORKLOAD / "build-result.json")
        approved = pinned(WORKLOAD / "approval-bundle.json")
        source = pinned(WORKLOAD / "runtime-install-review.json")
        if (parent["parent_review_sha256"] != INPUTS[WORKLOAD / "approval-bundle.json"]
                or not parent["passed"] or not parent["parent_layers_verified"]
                or not parent["inherited_config_verified"] or not approved["build_context"]
                or not source["complete_static_dependency_closure"]):
            raise ValueError("retained Django artifact lineage differs")
        triage = pinned(HERE / "repository-expansion-runtime-triage.json")
        expected, = [row for row in triage["cases"] if row["case"] == case]
        declared = expected["verified_portable_wheel_pins"]
        selected = {canonicalize_name(item["project"]): item for item in source["pins"]
                    if canonicalize_name(item["project"]) in declared}
        if (selected.keys() != declared.keys() or any(
            any(item[attr] != declared[name][attr] for attr in ("sha256", "private_cache", "size_bytes", "version"))
            for name, item in selected.items()
        )):
            raise ValueError("inherited Django dependency pins differ")
        inherited = [f"{name}=={item['version']}" for name, item in sorted(selected.items())]
        carrier = parent["image_id"]
        transport = WORK / "repository-expansion-acquisition" / "transport"
        inventory = json.loads(read(transport.parent / "index.json", acquisition["candidate_index_sha256"]))
        row, = [value for value in inventory if value["input"]["task_id"] == case]
        plugins = ["pytest_django.plugin"]
    if (row["input"]["task_id"] != case or row["source_revision"] != publisher["revision"]
            or row["input"]["source_sha256"] != publisher["source_sha256"]):
        raise ValueError("exact publisher source no longer matches")
    return row, transport, carrier, inherited, plugins


def configure(key):
    row, transport, carrier, installed, plugins = source_inputs(key)
    case_id = row["input"]["task_id"]
    name = f"c13-{key}-protected-audit-20261118"
    target = WORK / name
    runner.NAME, runner.FROZEN, runner.CARRIER = name, FROZEN, carrier
    runner.REVIEW, runner.APPROVAL = target / "operation-review.json", target / "approval.json"
    runner.RUN, runner.MAX_CALLS = target / "execution", 2
    identity_count = 18 if key == "opentelemetry" else 19
    failures = set()
    artifact_report = portable_assets(key)
    base_lock, wheels = wheel_probe_assets()
    wheels.extend(runner.asset(ROOT / item["path"], item["sha256"]) for item in artifact_report.values())
    task, truth, fixed, original, _ = bind(row, transport, wheels)
    truth = truth.model_copy(update={"pytest_plugins": plugins})
    required = json.loads(read(transport / "protected" / case_id / "required.json",
                               row["protected_assets"]["required.json"]["sha256"]))
    failures.update(required["published_fail_to_pass"])
    failures.add(row["protected_guard"])
    if (len(truth.pass_to_pass) != identity_count or truth.fail_to_pass or len(failures) < 2
            or not failures <= set(truth.pass_to_pass)):
        raise ValueError("protected test identities differ")
    case = {
        "case_id": case_id, "source_revision": row["source_revision"], "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"), "roles": {"reference": fixed, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": installed,
    }

    def expected_statuses(oracle, role):
        statuses = dict.fromkeys(oracle["pass_to_pass"], "PASSED")
        if role == "original":
            statuses.update(dict.fromkeys(failures, "FAILED"))
        return statuses

    def definitions():
        if Path(aeep.__file__).resolve().parents[2] != FROZEN or verification_source_digest(FROZEN) != SOURCE:
            raise ValueError("load the exact frozen observer through PYTHONPATH")
        runtime = FROZEN / "integrations/assessment-runtime"
        program = (runtime / "repository_suite_native_program.py").read_text().replace(
            "'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr((runtime / "repository_suite_native_capture.py").read_text()))
        if digest(program.encode()) != PINNED_OBSERVER:
            raise ValueError("retained protected observer changed")
        spec = ExecutorSpec(
            id="repository.suite.observe", capability="assessment.repository_suite@1", kind="command",
            description="Contained native pytest contract audit",
            config={"argv": ["python3", "-B", "-c", program], "argv_literal": True, "stdin_json": True,
                    "output": {"type": "json"}, "timeout_seconds": 30, "max_stdin_bytes": LARGE_PAYLOAD,
                    "max_output_bytes": 500_000},
        )
        env = AssessmentEnvironment(
            environment_id=name, kind="container", container_image=carrier, identity={"source": SOURCE},
            container_runtime=runner.DOCKER, container_socket=runner.SOCKET, memory_mb=512,
            process_limit=96, container_tmpfs_mb=64,
        )
        return spec, env, [case]

    async def review_fields():
        review, spec, env, cases = await BASE_REVIEW()
        previous = {"reference": row["reference_archive_sha256"],
                    "original": row.get("fault_archive_sha256", row.get("original_archive_sha256"))}
        for role, launch in zip(runner.ROLES, review["launches"], strict=True):
            if launch["required_tests"] != identity_count or (previous[role] is not None
                    and launch["archive_sha256"] != previous[role]):
                raise ValueError("ordinary transport changed the protected source or test archive")
        return review | {
            "schema_version": "aeep.c13.expansion-contract-audit.v1",
            "bindings": {path.relative_to(ROOT).as_posix(): sha for path, sha in INPUTS.items()},
            "wrapper_sha256": file_digest(Path(__file__)), "baseline_wheel_review_sha256": base_lock,
            "portable_inventory": artifact_report, "expected_original_failures": sorted(failures),
            "minimum_host_free_bytes": 52 * 1024**3, "installations": 0, "network": False,
            "authority_scope": "First native protected grade of the bound upstream snapshot. No retry.",
        }, spec, env, cases

    runner.definitions, runner.review_fields, runner.expected_statuses = definitions, review_fields, expected_statuses


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("opentelemetry", "django-guardian"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--acquire-portable", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.acquire_portable:
        print(json.dumps(portable_assets(args.case, fetch=True), indent=2, sort_keys=True))
        return
    configure(args.case)
    if args.exact_review:
        raise SystemExit(0 if await runner.run(args.exact_review) else 1)
    review, *_ = await runner.review_fields()
    if args.prepare:
        runner.REVIEW.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        runner.put(runner.REVIEW, review | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    elif review != {key: value for key, value in runner.get(runner.REVIEW).items() if key != "expires_at"}:
        raise ValueError("staged execution review differs")
    print(file_digest(runner.REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
