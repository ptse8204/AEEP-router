"""Exercise the first canonical component using the existing bounded grant."""

import argparse
import contextlib
import hashlib
import io
import json
import re
import runpy
import shutil
import subprocess
from pathlib import Path

from aeep.assessment.models import AssessmentScopeAmendment, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main
from aeep_toolkit.stack_readiness import IntegrationEvidence
from aeep_toolkit.stack_verification import VerificationDefinitions, define

HERE = Path(__file__).resolve().parent
C13 = HERE.parent
ROOT = HERE.parents[3]
DELEGATION = C13 / "pipeline-standing-authority-20261104.json"
build = runpy.run_path(str(HERE / "sponsors-definition.py"))["build"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def invoke(args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(args) == 0
    return json.loads(out.getvalue())


def counters(store, authorization_id):
    return list(store._connection.execute(
        "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?",
        (authorization_id,),
    ).fetchone())


def review(folder):
    assert folder.is_dir() and not (folder / "sponsors-started.json").exists()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    bundle = build()
    bundle_file = folder / "sponsors-definitions.json"
    assert VerificationDefinitions.model_validate_json(bundle_file.read_bytes()) == bundle
    delegation = json.loads(DELEGATION.read_bytes())
    assert "first_attempts" in delegation and "repetitions" in delegation
    prior = C13 / "skillsbench-software-substitute-20261109/managed-preparation/managed-engineering/operation-review.json"
    database = json.loads(prior.read_bytes())["database"]
    env = bundle.environment
    request = next(iter(bundle.requests.values()))
    assert env is not None and env.container_image and env.container_socket
    # Reuse the already reviewed daemon and image. Inspect before any reservation.
    image = json.loads(subprocess.check_output(
        [env.container_runtime, "--host", "unix://" + env.container_socket, "image", "inspect", env.container_image],
        timeout=10,
    ))[0]
    assert image["Id"] == env.container_image and not image["Config"].get("Volumes")
    for check in bundle.checks.values():
        argv = check.executor.config["argv"]
        result = subprocess.run([shutil.which("python3"), *argv[1:]], capture_output=True, timeout=10)
        assert result.returncode == 0 and json.loads(result.stdout) == check.expected
    with ReceiptStore(":memory:") as copy, ReceiptStore(database, read_only=True) as live:
        live._connection.backup(copy._connection)
        repo = AssessmentRepository(copy)
        refs = define(repo, bundle, bundle.integration.implementation_source)
        original = repo.get("authorization", request.authorization_id)
        bindings = [
            ("subject", request.subject_digest), ("recipe", request.recipe_digest),
            ("environment", request.environment_digest), ("toolkit_integration_definition", refs["definition_ref"]),
            *[("boundary_probe_definition", ref) for ref in refs["checks"].values()],
        ]
        amendment = AssessmentScopeAmendment(
            amendment_id="canonical-sponsors-" + refs["definition_ref"][:20],
            authorization_id=request.authorization_id, authorization_digest=content_digest(original),
            subject_digests=[request.subject_digest], recipe_digests=[request.recipe_digest],
            environment_digests=[request.environment_digest], reviewed_digests=[ref for _, ref in bindings],
        )
        apply(repo, amendment, bindings)
        initial = counters(copy, request.authorization_id)
        for item in bundle.requests.values():
            grant = repo.authorize(item)
            assert grant.limits.max_cash_usd == 0
            assert initial[0] + 2 <= grant.limits.max_operations
            assert initial[2] + 130 <= grant.limits.max_elapsed_seconds
        return {
            "scope": "First canonical Sponsors source-attribution and authorized-link probes",
            "refs": refs, "amendment": amendment.model_dump(mode="json"),
            "bindings": bindings, "initial_counters": initial, "database": database,
            "bound_files": {str(path): sha(path) for path in [
                bundle_file, DELEGATION, Path(__file__), HERE / "sponsors-definition.py", prior,
            ]},
            "current_source": bundle.integration.implementation_source,
            "existing_image": env.container_image, "container_runtime": env.container_runtime,
            "maximum_operations": 2, "maximum_reserved_seconds": 130, "maximum_model_turns": 0,
            "maximum_cash_usd": "0", "network": False, "deletion": "only verified owned probe containers",
            "installs_builds_downloads": 0, "automatic_retry": False, "comparisons": "PAUSED",
        }


def apply(repo, amendment, bindings):
    with repo.store._lock:
        for _, ref in bindings:
            state = repo.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (ref,),
            ).fetchone()
            assert state is None or not state[0], "Preserve revoked reviews"
    repo.approve_bundle(amendment, {ref: repo.get(kind, ref) for kind, ref in bindings})


def execute(folder, review_file, expected):
    spec = json.loads(review_file.read_bytes())
    assert re.fullmatch(r"[0-9a-f]{64}", expected) and sha(review_file) == expected
    for name, digest in spec["bound_files"].items():
        assert sha(Path(name)) == digest
    fresh = json.loads(json.dumps(review(folder), default=str))
    fresh["amendment"]["issued_at"] = spec["amendment"]["issued_at"]
    assert fresh == spec
    reference = spec["refs"]["definition_ref"]
    database = ["--store", spec["database"]]
    bundle = folder / "sponsors-definitions.json"
    write(folder / "sponsors-started.json", {"review_sha256": expected, "comparisons": "PAUSED"})
    observations = {}
    result = {"review_sha256": expected, "comparisons": "PAUSED", "passed": False}
    try:
        assert invoke(["stack-verify", "define", *database, "--file", str(bundle)]) == spec["refs"]
        amendment = AssessmentScopeAmendment.model_validate(spec["amendment"])
        with ReceiptStore(spec["database"]) as store:
            assert counters(store, amendment.authorization_id) == spec["initial_counters"]
            apply(AssessmentRepository(store), amendment, spec["bindings"])
        for name, request_id in spec["refs"]["requests"].items():
            observation = invoke(["stack-verify", "probe", *database, "--component", "github-sponsors",
                                  "--check", name, "--definition-ref", reference, "--request-id", request_id])
            observations[name] = observation
            write(folder / f"sponsors-{name}-probe.json", observation)
        evidence = IntegrationEvidence(definition_ref=reference, probe_refs={
            name: row["probe_ref"] for name, row in observations.items()
        })
        record_file = folder / "sponsors-evidence.json"
        write(record_file, evidence.model_dump(mode="json"))
        result["record"] = invoke(["stack-verify", "record", *database, "--component", "github-sponsors",
                                   "--file", str(record_file)])
        readiness = invoke(["stack-status", *database])
        sponsor = next(row for row in readiness["components"] if row["component"] == "github-sponsors")
        assert sponsor["functional_status"] == "VERIFIED"
        assert all(check["receipt_ref"] for check in sponsor["checks"].values())
        result.update(passed=True, component=sponsor)
    finally:
        result["observations"] = observations
        with ReceiptStore(spec["database"], read_only=True) as store:
            result["final_counters"] = counters(store, spec["amendment"]["authorization_id"])
            assert result["final_counters"][0] - spec["initial_counters"][0] <= 2
            assert result["final_counters"][1] == spec["initial_counters"][1]
            assert result["final_counters"][3] == spec["initial_counters"][3]
        write(folder / "sponsors-result.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute-delegated")
    args = parser.parse_args()
    folder = args.work.resolve(strict=True)
    review_file = folder / "sponsors-operation-review.json"
    if args.prepare:
        write(review_file, review(folder))
        print(sha(review_file))
    else:
        execute(folder, review_file, args.execute_delegated)
