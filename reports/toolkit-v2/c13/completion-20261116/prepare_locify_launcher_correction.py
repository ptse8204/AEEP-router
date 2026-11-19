"""Freeze the copy-only Locify launcher repair and its protected repeat scope."""

import argparse
import subprocess
from datetime import timedelta
from pathlib import Path

import check_eos_native_runtime as eos
import check_locify_protected_pair as locify
import check_locify_source_wheels as journal
from check_repository_launcher import PROBE
from stage_repository_transport import WORK, encode, write

from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now

NAME = "c13-locify-ordinary-launcher-correction-20261119"
TARGET = WORK / NAME
OLD = locify.RUNTIME / "result.json"
OLD_ATTEMPT = locify.TARGET / "execution"
OLD_TAG = "aeep-toolkit-v2/locify-runtime:fb523b79-cp312-20261119"
TAG = "aeep-toolkit-v2/locify-grader:fb523b79-launcher-20261119"
CONTEXT = TARGET / "context"
REVIEW = TARGET / "operation-review.json"
SITE = "/usr/local/lib/python3.13/site-packages"


def prepare():
    if REVIEW.exists():
        raise ValueError("exact correction review already exists")
    old = journal.doc(OLD)
    report = journal.doc(OLD_ATTEMPT / "result.json")
    if not old["passed"] or report["verified"] or len(report["observations"]) != 1:
        raise ValueError("Locify terminal boundary changed")
    docker, env = journal.docker_settings()
    parents = {tag: journal.inspect(docker, env, tag) for tag in (OLD_TAG, eos.GRADER)}
    if parents[OLD_TAG] != old["image"]:
        raise ValueError("Locify CPython 3.12 runtime changed")
    smoke_path = WORK / "c13-repository-launcher-smoke-20261119/result.json"
    observed = journal.doc(smoke_path)["observations"]
    eos_runtime = journal.doc(eos.REVIEW)
    if (observed["locify"]["missing_module"] != "pydantic" or not observed["eos"]["worker_import"]
            or parents[eos.GRADER] != eos_runtime["sources"][eos.GRADER]):
        raise ValueError("the diagnosis or validated launcher source changed")
    for parent in parents.values():
        if subprocess.check_output([*docker, "image", "inspect", parent["id"], "--format",
                                    '{{range .Config.Env}}{{println .}}{{end}}'],
                                   env=env, timeout=15, text=True).splitlines().count("PYTHON_VERSION=3.13.15") != 1:
            raise ValueError("both carriers must use the same CPython 3.13 ABI")
    recipe = (f"FROM {eos.GRADER} AS launcher\nFROM {OLD_TAG}\n"
              f"COPY --from=launcher {SITE}/ {SITE}/\n")
    write(CONTEXT / "Dockerfile", recipe.encode())
    old_review = journal.doc(locify.TARGET / "operation-review.json")
    if not all(launch["operation"].endswith(role) for launch, role in zip(
            old_review["launches"], ("reference", "original"), strict=True)):
        raise ValueError("reviewed protected roles drifted")
    build = [*docker, "build", "--pull=false", "--network=none", "--platform=linux/arm64",
             "--provenance=false", "--sbom=false", "--tag", TAG, str(CONTEXT)]
    usage = subprocess.check_output([*docker, "system", "df"], env=env, text=True, timeout=30)
    document = {
        "schema_version": "aeep.c13.locify-ordinary-launcher-repeat-review.v1",
        "source_digest": verification_source_digest(locify.VERIFIED_SOURCE),
        "prepare_driver_sha256": journal.fingerprint(Path(__file__)),
        "docker_pins": journal.docker_pins(docker), "docker_usage": usage,
        "prior_review_sha256": report["review_sha256"],
        "prior_result_sha256": journal.fingerprint(OLD_ATTEMPT / "result.json"),
        "prior_ledger_sha256": journal.fingerprint(OLD_ATTEMPT / "ledger.json"),
        "launcher_observation_sha256": journal.fingerprint(smoke_path),
        "parents": parents, "dockerfile_sha256": journal.fingerprint(CONTEXT / "Dockerfile"),
        "build": {"argv": build, "environment": env, "output_tag": TAG, "deadline_seconds": 150,
                  "verify_lineage_before_use": parents[OLD_TAG]},
        "pre_grade_checks": {"command": ["python3", "-I", "-B", "-c", PROBE],
            "required": ["verified added local image layer", "ordinary worker import", "same Python 3.13 ABI"],
            "network": "none", "uid_gid": "65534:65534", "deadline_seconds": 30},
        "grade_roles": [dict(operation=row["operation"], archive_sha256=row["archive_sha256"],
            payload_sha256=row["payload_sha256"], required_tests=row["required_tests"]) for row in old_review["launches"]],
        "observer_fingerprint": old_review["observer_fingerprint"],
        "grade_boundary": old_review["environment"],
        "only_grade_environment_change": "Replace old image identity with the verified child image.",
        "minimum_build_free_bytes": 53 * 2**30, "minimum_grade_free_bytes": 52 * 2**30,
        "limits": {"operations": 4, "reserved_seconds": 260, "model_turns": 0, "cash_usd": 0},
        "expires_at": (utc_now() + timedelta(days=3)).isoformat(),
        "retained_original_charges": 1, "automatic_retries": 0, "provider_disclosure": False,
        "downloads": 0, "remove_existing_resources": False, "require_operator_approval_for_repeat": True,
    }
    write(REVIEW, encode(document))
    print(journal.fingerprint(REVIEW))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", required=True)
    parser.parse_args()
    prepare()


if __name__ == "__main__":
    main()
