"""Check carrier launcher imports without running any repository task or test."""

import argparse
import asyncio
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import check_locify_source_wheels as journal
from check_locify_protected_pair import VERIFIED_SOURCE
from stage_repository_transport import ROOT, WORK, encode, write

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep.store import ReceiptStore

NAME = "c13-repository-launcher-smoke-20261119"
TARGET = WORK / NAME
REVIEW = TARGET / "operation-review.json"
LIMITS = AssessmentLimits(max_operations=2, max_elapsed_seconds=60)
SOURCES = {
    "locify": WORK / "locify-installed-runtime-20261119/result.json",
    "eos": WORK / "c13-eos-native-runtime-20261119/result.json",
}
PROBE = """import importlib.util, json, re, sys
names = ('pydantic', 'psutil', 'jsonschema', 'rfc8785', 'cryptography', 'httpx', 'yaml', 'opentelemetry')
result = {'python': list(sys.version_info[:2]), 'present': {n: importlib.util.find_spec(n) is not None for n in names}}
sys.path.insert(0, '/opt/aeep-source')
try:
    from aeep.assessment.container_worker import run
except ModuleNotFoundError as error:
    name = str(error.name)
    result['missing_module'] = name if re.fullmatch(r'[A-Za-z_][A-Za-z_.0-9]*', name) else 'unexpected'
    result['worker_import'] = False
else:
    result['worker_import'] = callable(run)
print(json.dumps(result))
"""


def fields():
    docker, env = journal.docker_settings()
    cases = {}
    mount = "type=bind,src=" + str(VERIFIED_SOURCE / "src") + ",dst=/opt/aeep-source,readonly"
    for role, path in SOURCES.items():
        image = journal.doc(path)["image"]["id"]
        identity = journal.inspect(docker, env, image)
        owned = f"{NAME}-{role}"
        if subprocess.check_output([*docker, "ps", "-aq", "--filter", f"name=^/{owned}$"],
                                   env=env, timeout=10).strip():
            raise ValueError("smoke container identity is already in use")
        cases[role] = {"image": identity, "name": owned, "argv": [
            *docker, "run", "--pull=never", "--rm", "--name", owned, "--network=none",
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user=65534:65534", "--memory=256m", "--memory-swap=256m", "--pids-limit=32",
            "--mount", mount, "--entrypoint", "python3", image, "-I", "-B", "-c", PROBE,
        ]}
    return {
        "schema_version": "aeep.c13.repository-launcher-smoke.v1",
        "cases": cases, "env": env, "driver_sha256": journal.fingerprint(Path(__file__)),
        "journal_sha256": journal.fingerprint(Path(journal.__file__)),
        "authority_sha256": journal.fingerprint(journal.AUTHORITY),
        "docker_pins": journal.docker_pins(docker), "source_digest": verification_source_digest(VERIFIED_SOURCE),
        "limits": LIMITS.model_dump(mode="json"), "models": 0, "cash_usd": 0,
        "protected_replays": 0, "runtime_changes": 0, "minimum_free_bytes": 50 * 2**30,
    }


def preflight(exact):
    review = journal.doc(REVIEW)
    expiry = datetime.fromisoformat(review["expires_at"])
    if (journal.fingerprint(REVIEW) != exact or review != fields() | {"expires_at": review["expires_at"]}
            or (TARGET / "started.json").exists() or shutil.disk_usage(ROOT).free <= review["minimum_free_bytes"]
            or utc_now() >= expiry):
        raise ValueError("first launcher-only smoke scope drifted")
    return review, expiry


async def execute(exact):
    review, expiry = await asyncio.to_thread(preflight, exact)
    scope = journal.Scope(review_sha256=exact)
    key = content_digest(scope)
    request = RecipeMaterializationRequest(plan_id=NAME, authorization_id=NAME,
        subject_digest=key, recipe_digest=key, mapping_digest=key, environment_digest=key,
        definition_digests=[key], seed=0)
    grant = AssessmentAuthorization(authorization_id=NAME, subject_digests=[key], recipe_digests=[key],
        environment_digests=[key], allowed_destinations=["local"], expires_at=expiry,
        limits=LIMITS, remote_disclosure=False)
    journal.HOME_DIR, journal.LABEL = TARGET, NAME
    write(TARGET / "started.json", encode({"review": exact, "first_attempt": True}))
    results = {}
    with ReceiptStore(TARGET / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_launcher_smoke_scope", key, scope)
        repo.approve_bundle(grant, {key: scope.model_dump(mode="json")})
        try:
            for role, case in review["cases"].items():
                raw = await journal.run_operation(repo, store, request, case["argv"], role, 25, exact, review["env"])
                results[role] = json.loads(raw.stdout)
        finally:
            write(TARGET / "ledger.json", encode(repo.operation_ledger(NAME).model_dump(mode="json")))
            write(TARGET / "result.json", encode({"review": exact, "observations": results}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--first-review")
    args = parser.parse_args()
    if args.prepare:
        if REVIEW.exists():
            raise ValueError("scope already exists")
        write(REVIEW, encode(fields() | {"expires_at": (utc_now() + timedelta(hours=2)).isoformat()}))
        print(journal.fingerprint(REVIEW))
    else:
        asyncio.run(execute(args.first_review))


if __name__ == "__main__":
    main()
