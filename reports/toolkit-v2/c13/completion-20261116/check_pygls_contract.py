"""Verify the staged PyGLS standard-I/O contract on the retained offline grader."""

import argparse
import asyncio
import inspect
import json
import tomllib
from collections import Counter
from datetime import timedelta
from pathlib import Path
from urllib.request import build_opener

import repository_offline_pair_batch as runner
from acquire_larger_multifile_source import AUTHORITY, binding
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_advanced_alchemy_pair import FROZEN, SOURCE, verify_source
from check_expansion_contracts import NoRedirect, inspect_wheel
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from stage_repository_transport import ROOT, WORK, digest, read

from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.stack_verification import ROOT as CURRENT_ROOT

CASE = "openlawlibrary__pygls-524-aeep-contract-audit"
NAME = "c13-pygls-contract-20261118"
TARGET = WORK / NAME
INDEX = WORK / "ancillary-contract-audits/index.json"
INDEX_SHA = "668b21cc6493bbffc4a54fd622c63ef304f9953fd7853ba8b7651f536f556d3a"
AUTHORITY_SHA = "f0f86d6af2600817eb6de50dd12ac4f861f09ac36f90a27bc84e4ae6f044635c"
WHEEL_ROOT = "https://files.pythonhosted.org/packages/"
# Digests come from the source lock. The publisher metadata supplied the routes and sizes.
DOWNLOADS = {
    "attrs": (
        "24.2.0",
        63_001,
        "6a/21/5b6702a7f963e95456c0de2d495f67bf5fd62840ac655dc451586d23d39a",
    ),
    "cattrs": (
        "24.1.2",
        66_446,
        "c8/d5/867e75361fc45f6de75fe277dd085627a9db5ebb511a87f27dc1396b5351",
    ),
    "lsprotocol": (
        "2024.0.0b1",
        76_600,
        "4d/1b/526af91cd43eba22ac7d9dbdec729dd9d91c2ad335085a61dd42307a7b35",
    ),
    "pytest-asyncio": (
        "0.24.0",
        18_024,
        "96/31/6607dab48616902f76885dfcf62c08d929796fc3b2d2318faf9fd54dbed9",
    ),
}
BASE_REVIEW, BASE_PROBE = runner.review_fields, runner.verify_probe
CORE = {"pytest": "8.3.5", "packaging": "25.0", "iniconfig": "2.1.0", "pluggy": "1.6.0"}
CONTINUATION = WORK.parent / "c13-cohort-runtime-20261124/pygls"
CONTINUATION_SOURCE = "2896e52509b33a5628f8d5833a9b6111ebff9f0ed374faa08da539a57753c896"
NATIVE_COLLECTION = CONTINUATION.parent / "pygls-native-identities/result.json"
NATIVE_COLLECTION_SHA = "943690d9689d7d8d2ccc2f665809dbe4fc91aae45b55ad04fabea74dd53b0f99"


def supports_checkout(origin_paths, wheels, repo):
    """Use the same reviewed dependency and source paths for fixture subprocesses."""
    return (
        f";os.environ['PYTHONPATH']=os.pathsep.join({origin_paths!r});"
        "from importlib.metadata import version;"
        f"assert all(version(n)==v for n,v in {wheels!r}.items());"
        "import importlib.util;"
        f"assert importlib.util.find_spec('pygls').origin=={str(repo / 'pygls/__init__.py')!r}"
    )


def locked_runtime(source, *, fetch):
    lock = {item["name"]: item for item in tomllib.loads(source["poetry.lock"].decode())["package"]}
    versions = CORE | {name: pin[0] for name, pin in DOWNLOADS.items()}
    read(AUTHORITY, AUTHORITY_SHA)
    output = {}
    for name, (version, size, route) in DOWNLOADS.items():
        filename = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
        package = lock[name]
        (item,) = [item for item in package["files"] if item["file"] == filename]
        if package["version"] != version:
            raise ValueError("publisher lock version differs")
        sha = item["hash"].removeprefix("sha256:")
        path = TARGET / "wheels" / filename
        url = f"{WHEEL_ROOT}{route}/{filename}"
        if fetch and not path.exists():
            with build_opener(NoRedirect()).open(url, timeout=12) as response:
                data = response.read(size + 1)
            if len(data) != size or digest(data) != sha:
                raise ValueError("publisher payload differs from the locked file")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
            path.chmod(0o400)
        if len(read(path, sha)) != size:
            raise ValueError("locked asset size differs")
        review = inspect_wheel(path, name, sha, version)
        for value in review["active_requires_dist"]:
            req = Requirement(value)
            actual = versions.get(canonicalize_name(req.name))
            if req.url or req.extras or actual is None or actual not in req.specifier:
                raise ValueError(f"runtime dependency is outside the profile: {req}")
        output[name] = review | {"publisher_url": url}
    return versions, output


def protected_inputs():
    (row,) = [row for row in json.loads(read(INDEX, INDEX_SHA)) if row["input"]["task_id"] == CASE]
    base_pin, wheels = wheel_probe_assets()
    task, truth, *_ = bind(row, INDEX.parent, wheels)
    source = archive_files(truth.source.read(), large=True)
    notices = row["license_notices"]
    for item in notices:
        body = source[item["file"]]
        if len(body) != item["bytes"] or digest(body) != item["sha256"]:
            raise ValueError("source license notice differs from the reviewed archive")
    required = json.loads(
        read(
            INDEX.parent / "protected" / CASE / "required.json",
            row["protected_assets"]["required.json"]["sha256"],
        )
    )
    negative = [*required["published_fail_to_pass"], row["protected_guard"]]
    if len(truth.pass_to_pass) != 87 or len(negative) != 5 or truth.fail_to_pass:
        raise ValueError("protected identity inventory differs")
    return row, task, source, base_pin, wheels, negative


def recover_native_identities(required, collected):
    """Match truncated labels to the remaining exact node IDs."""
    unmatched = set(collected) - set(required)
    missing = set(required) - set(collected)
    if len(unmatched) != len(missing) or len(collected) != len(set(collected)):
        raise ValueError("the declared and native test sets differ in size")
    bindings = {}
    for prefix in sorted(missing, key=lambda value: (-len(value), value)):
        candidates = [node for node in unmatched if node.startswith(prefix) and node.endswith("]")]
        if len(candidates) != 1 or prefix.count("[") <= prefix.count("]"):
            raise ValueError("truncated publisher label has no unique native match")
        bindings[prefix] = candidates[0]
        unmatched.remove(candidates[0])
    return bindings


def configure(observations, *, timed_stdio=False, resolved_identities=False):
    root, source_digest, name, destination = FROZEN, SOURCE, NAME, TARGET
    if timed_stdio:
        root, source_digest = CURRENT_ROOT, CONTINUATION_SOURCE
        name, destination = "c13-pygls-stdio-countdowns-20261124", CONTINUATION
        if verification_source_digest(root) != source_digest:
            raise ValueError("use the verified current coordinator")
        if resolved_identities:
            name += "-native-identities"
            destination = CONTINUATION.parent / "pygls-verified-pair-50gib"
    else:
        verify_source()
    row, _, source, base_pin, wheels, negative = protected_inputs()
    versions, pins = locked_runtime(source, fetch=False)
    wheels.extend(runner.asset(ROOT / item["path"], item["sha256"]) for item in pins.values())
    task, truth, reference, original, _ = bind(row, INDEX.parent, wheels)
    truth = truth.model_copy(update={"pytest_plugins": ["pytest_asyncio.plugin"]})

    runtime = root / "integrations/assessment-runtime"
    program = (
        (runtime / "repository_suite_native_program.py")
        .read_text()
        .replace(
            "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
            repr((runtime / "repository_suite_native_capture.py").read_text()),
        )
    )
    anchor = "+ ';os.chdir('"
    if program.count(anchor) != 1:
        raise ValueError("reviewed bootstrap changed")
    bootstrap = f"({supports_checkout.__name__}([*wheels, str(repo / 'src'), str(repo)], {versions!r}, repo))"
    # Inline a tiny, deterministic bootstrap for the child Python process.
    program = program.replace(
        "def main():", inspect.getsource(supports_checkout) + "\n\ndef main():"
    )
    program = program.replace(anchor, f"+ {bootstrap}\n            " + anchor)
    if timed_stdio:
        # The blocking and threaded countdown fixtures each sleep for 10 seconds.
        # Budget both serial tests plus the unmodified stdio suite and fixture teardown.
        if program.count("timeout=22, check=False") != 1:
            raise ValueError("native pytest timeout anchor changed")
        program = program.replace("timeout=22, check=False", "timeout=55, check=False")
    compile(program, "<PyGLS protected observer>", "exec")

    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Contained PyGLS standard-I/O native grader",
        config={
            "argv": ["python3", "-B", "-c", program],
            "argv_literal": True,
            "stdin_json": True,
            "timeout_seconds": 65 if timed_stdio else 32,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
            "output": {"type": "json"},
        },
    )
    environment = AssessmentEnvironment(
        environment_id=name,
        kind="container",
        network=False,
        container_image=runner.CARRIER,
        identity={"source": source_digest, "source_index": INDEX_SHA},
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )
    subject = {
        "case_id": CASE,
        "source_revision": row["source_revision"],
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [],
    }
    historical_subject = content_digest(subject)
    substitutions = {}
    if resolved_identities:
        collection = json.loads(read(NATIVE_COLLECTION, NATIVE_COLLECTION_SHA))
        substitutions = recover_native_identities(truth.pass_to_pass, collection["native_ids"])
        if (
            len(substitutions) != 5
            or collection["grade_executed"]
            or any(
                node not in collection["missing_prefix_matches"][old]
                for old, node in substitutions.items()
            )
            or substitutions.keys() & set(negative)
        ):
            raise ValueError("native collection changed the required assertion scope")
        subject["truth"]["pass_to_pass"] = [
            substitutions.get(item, item) for item in truth.pass_to_pass
        ]

    def expected_statuses(truth, role):
        statuses = dict.fromkeys(truth["pass_to_pass"], "PASSED")
        if role == "original":
            statuses.update(dict.fromkeys(negative, "FAILED"))
        return statuses

    def observe(reply, payload, expected, code):
        accepted = BASE_PROBE(reply, payload, expected, code)
        record = {
            "role": "original" if code else "reference",
            "verified_contract": accepted,
            "archive_sha256": payload["archive_sha256"],
        }
        if isinstance(reply, dict) and isinstance(reply.get("statuses"), dict):
            statuses = reply["statuses"]
            allowed = {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
            if len(statuses) <= 10000 and all(
                isinstance(status, str) and status in allowed for status in statuses.values()
            ):
                record |= {
                    "pytest_exit": reply.get("exit_code"),
                    "required_status_counts": dict(
                        Counter(statuses.get(node, "MISSING") for node in expected)
                    ),
                    "mismatch_identities": [
                        {
                            "node_id": node,
                            "observed": statuses.get(node, "MISSING"),
                            "expected": want,
                        }
                        for node, want in expected.items()
                        if statuses.get(node) != want
                    ],
                }
        observations.append(record)
        return accepted

    async def review_fields():
        fields, *_ = await BASE_REVIEW()
        if [call["required_tests"] for call in fields["launches"]] != [87, 87]:
            raise ValueError("protected launch identities differ")
        continuation = {}
        if timed_stdio:
            previous = runner.get(TARGET / "operation-review.json")
            diagnosis_path = TARGET / "timeout-diagnostic/execution/worker-diagnostic.json"
            diagnosis = runner.get(diagnosis_path)
            if (
                diagnosis["observer_category"] != "child_timeout"
                or diagnosis["last_required_test"]
                != "tests/e2e/test_threaded_handlers.py::test_countdown_threaded"
                or fields["carrier_layers"] != previous["carrier_layers"]
                or {CASE: historical_subject} != previous["case_fingerprints"]
                or any(
                    probe[key] != retained[key]
                    for probe, retained in zip(
                        fields["launches"], previous["launches"], strict=True
                    )
                    for key in ("archive_sha256", "payload_sha256", "required_tests")
                )
            ):
                raise ValueError("the timed stdio review must retain the original case")
            continuation = {
                "terminal_timeout_receipt": binding(diagnosis_path),
                "prior_review": binding(TARGET / "operation-review.json"),
                "inner_timeout_seconds": 55,
                "worker_timeout_seconds": 65,
            }
            if resolved_identities:
                deferred = CONTINUATION.parent / "pygls-verified-pair"
                if (deferred / "execution").exists():
                    raise ValueError("recover the prior pair before authorizing another launch")
                continuation |= {
                    "native_collection": binding(NATIVE_COLLECTION),
                    "prior_timed_review": binding(CONTINUATION / "operation-review.json"),
                    "exact_selector_bindings": substitutions,
                    "preflight_only_review": binding(deferred / "operation-review.json"),
                    "storage_floor_bytes": 50 * 2**30,
                    "storage_basis": "Read-only retained image, 64 MiB of per-container tmpfs and bounded output. No install, rebuild, download or deletion.",
                }
        return (
            fields
            | {
                "schema_version": "aeep.c13.pygls-protected-audit.v1",
                "driver": binding(Path(__file__)),
                "delegated_authority": binding(AUTHORITY),
                "index_sha256": INDEX_SHA,
                "source_license_notices": row["license_notices"],
                "baseline_wheel_review_sha256": base_pin,
                "locked_wheels": pins,
                "lock_sha256": digest(source["poetry.lock"]),
                "original_expected_failures": negative,
                "transport": "Upstream CPython/stdio defaults with exact private Python paths. Optional TCP, WebSocket and Pyodide transports are outside the audited case.",
                "comparisons_paused": True,
                "waza_excluded": True,
            }
            | continuation,
            spec,
            environment,
            [subject],
        )

    runner.NAME, runner.FROZEN, runner.MAX_CALLS = name, root, 2
    if timed_stdio:
        runner.ROLE_SECONDS = 75
    runner.REVIEW = destination / "operation-review.json"
    runner.APPROVAL = destination / "approval.json"
    runner.RUN = destination / "execution"
    runner.definitions = lambda: (spec, environment, [subject])
    runner.review_fields, runner.verify_probe, runner.expected_statuses = (
        review_fields,
        observe,
        expected_statuses,
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--acquire", action="store_true")
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--exact-review")
    parser.add_argument("--timed-stdio", action="store_true")
    parser.add_argument("--resolved-identities", action="store_true")
    args = parser.parse_args()
    if args.resolved_identities and not args.timed_stdio:
        parser.error("--resolved-identities requires --timed-stdio")
    if args.acquire:
        _, _, source, *_ = protected_inputs()
        versions, pins = locked_runtime(source, fetch=True)
        print(json.dumps({"versions": versions, "pins": pins}, sort_keys=True, indent=2))
        return
    observations = []
    configure(
        observations, timed_stdio=args.timed_stdio, resolved_identities=args.resolved_identities
    )
    if args.prepare:
        review, *_ = await runner.review_fields()
        if runner.REVIEW.exists() or runner.RUN.exists():
            raise ValueError("preserve the original review and execution")
        if args.timed_stdio:
            runner.REVIEW.parent.mkdir(parents=True, mode=0o700)
        runner.put(
            runner.REVIEW,
            review | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()},
        )
        print(runner.file_digest(runner.REVIEW))
    else:
        try:
            passed = await runner.run(args.exact_review)
        finally:
            if observations and runner.RUN.exists():
                runner.put(runner.RUN / "required-test-observations.json", observations)
        raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
