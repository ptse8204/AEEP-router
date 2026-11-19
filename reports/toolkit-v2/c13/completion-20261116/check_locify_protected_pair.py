"""Bind Locify to the ordinary v7 grader and its verified offline runtime."""

import argparse
import asyncio
import json
from datetime import timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

import aeep
from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.assessment.repository_suites import (
    LARGE_PAYLOAD,
    SuiteAssetV5,
    SuiteInput,
    SuiteTruthV7,
    archive_files,
    compressed_patch_artifact,
    pack_files,
)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.models import ExecutorSpec, utc_now

CASE = "ryanhoangt__locify-8"
NAME = "c13-locify-protected-pair-20261119"
TARGET = WORK / NAME
VERIFIED_SOURCE = ROOT / ".aeep/c13-combined-full-verification.4ae1bc40/source"
ASSETS = WORK / "locify-locked-runtime-assets-20261119"
RUNTIME = WORK / "locify-installed-runtime-20261119"
AUTHORITY = HERE.parent / "pipeline-standing-authority-20261104.json"
BASE_REVIEW = runner.review_fields
BASE_PROBE = runner.verify_probe
OBSERVER = Path(__file__).resolve()


def load(path):
    return json.loads(path.read_bytes())


def asset(record):
    return read(ROOT / record["path"], record["sha256"])


def spec():
    directory = VERIFIED_SOURCE / "integrations/assessment-runtime"
    program = (directory / "repository_suite_native_program.py").read_text().replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'", repr((directory / "repository_suite_native_capture.py").read_text()))
    anchor = "'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'"
    if program.count(anchor) != 1:
        raise ValueError("ordinary observer environment changed")
    program = program.replace(anchor, anchor + (
        ", 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',"
        " 'TIKTOKEN_CACHE_DIR': '/opt/c13-locify-tokenizer', 'HF_HUB_OFFLINE': '1'"
    ))
    compile(program, "<Locify ordinary observer>", "exec")
    return ExecutorSpec(
        id="repository.suite.observe", capability="assessment.repository_suite@1", kind="command",
        description="Ordinary native observations with pinned offline tokenizer inputs.",
        config={"argv": ["/opt/c13-locify/bin/python", "-B", "-c", program], "argv_literal": True,
                "stdin_json": True, "timeout_seconds": 30, "max_stdin_bytes": LARGE_PAYLOAD,
                "max_output_bytes": 500_000, "output": {"type": "json"}},
    )


def make_case():
    origin = load(HERE / "full-rebench-three-leads-result-20261119.json")
    known = origin["cases"][CASE]
    (row,) = [item for item in json.loads(asset(origin["protected_staging"]))["cases"] if item["case"] == CASE]
    public = asset(row["assets"]["untouched-source"])
    overlay = asset(known["protected_overlay"])
    published = archive_files(asset(known["reference_archive"]), large=True)
    initial = archive_files(public, large=True)
    edits = sorted(set(row["source_changes"]) - {"pyproject.toml"} | set(row["source_additions"]))
    value = SuiteInput(task_id=CASE, task=asset(known["full_statement"]).decode(), family="repository-mapping",
                       source_sha256=digest(public), editable_paths=edits).model_dump(mode="json")
    base = content_digest(value)
    original = compressed_patch_artifact(RepositoryPatch(base_sha256=base, files={}))
    reference = compressed_patch_artifact(RepositoryPatch(
        base_sha256=base, files={name: published[name].decode() for name in edits}))
    truth_files = {"public": public, "tests": overlay}
    paths = {"public": TARGET / "public" / f"{digest(public)}.tar.gz", "tests": TARGET / "protected/tests.tar.gz"}
    for role, data in truth_files.items():
        if not paths[role].exists():
            write(paths[role], data)
        elif read(paths[role], digest(data)) != data:
            raise ValueError("staged case bytes changed")
    if set(row["source_additions"]) != set(edits) - initial.keys():
        raise ValueError("reviewed created module changed")
    expected_ref = pack_files(published | {"pyproject.toml": initial["pyproject.toml"]}, large=True)
    if digest(expected_ref) != load(WORK / "locify-creation-contract-20261119.json")["protected_reference_projection_sha256"]:
        raise ValueError("reviewed reference projection changed")
    tests = json.loads(asset(row["assets"]["required.json"]))
    (pytest_wheel,) = [item for item in load(ASSETS / "result.json")["downloaded"]
                       if Path(item["path"]).name == "pytest-8.3.3-py3-none-any.whl"]
    truth = SuiteTruthV7(
        input_sha256=base, source=SuiteAssetV5(path=str(paths["public"]), sha256=digest(public), size_bytes=len(public)),
        tests=SuiteAssetV5(path=str(paths["tests"]), sha256=digest(overlay), size_bytes=len(overlay)),
        wheels=[runner.asset(ROOT / pytest_wheel["path"], pytest_wheel["sha256"])],
        python="3.12", pytest="8.3.3", pytest_plugins=[], patch_encoding="gzip-json",
        test_roots=["tests"], test_paths=sorted({name.split("::")[0] for group in tests.values() for name in group}),
        archive_profile="repository-v1", identity_format="pytest-native-v1", create_paths=row["source_additions"], **tests,
    )
    return {"case_id": CASE, "input": value, "truth": truth.model_dump(mode="json"),
            "source_revision": known["source_revision"], "roles": {"reference": reference, "original": original},
            "reference_archive_sha256": digest(expected_ref), "existing_image_dependencies": ["65 reviewed runtime packages", "offline tokenizer", "Git"]}


def configure(observations):
    if Path(aeep.__file__).resolve().parents[2] != VERIFIED_SOURCE:
        raise ValueError("protected pair requires the verified staged v7 source")
    runtime = load(RUNTIME / "result.json")
    if not runtime["passed"]:
        raise ValueError("retained offline imports did not pass")
    runner.NAME, runner.FROZEN, runner.CARRIER, runner.MAX_CALLS = NAME, VERIFIED_SOURCE, runtime["image"]["id"], 2
    runner.REVIEW, runner.APPROVAL, runner.RUN = TARGET / "operation-review.json", TARGET / "approval.json", TARGET / "execution"
    program = spec()
    env = AssessmentEnvironment(
        environment_id=NAME, kind="container", identity={"runtime_review": runtime["review_sha256"]}, network=False,
        container_image=runner.CARRIER, container_runtime=runner.DOCKER, container_socket=runner.SOCKET,
        memory_mb=768, process_limit=96,
    )
    case = make_case()
    runner.definitions = lambda: (program, env, [case])

    def probe(reply, payload, expected, code):
        accepted = BASE_PROBE(reply, payload, expected, code)
        statuses = reply.get("statuses") if isinstance(reply, dict) else None
        if isinstance(statuses, dict):
            observations.append({
                "role": "original" if code else "reference", "exit": reply.get("exit_code"),
                "required_statuses": {name: statuses.get(name, "MISSING") for name in expected},
                "protected_reply_sha256": content_digest(reply), "contract_matched": accepted,
            })
        return accepted

    runner.verify_probe = probe

    async def review():
        info, program, env, cases = await BASE_REVIEW()
        return info | {
            "schema_version": "aeep.c13.locify-protected-pair.v1",
            "dispatcher_sha256": digest(OBSERVER.read_bytes()), "operator_authority_sha256": digest(AUTHORITY.read_bytes()),
            "runtime_receipt_sha256": digest((RUNTIME / "result.json").read_bytes()),
            "result_scope": "Engineering reference and original checks only",
        }, program, env, cases

    runner.review_fields = review


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--first-review")
    args = parser.parse_args()
    observations = []
    configure(observations)
    if args.prepare:
        review, *_ = await runner.review_fields()
        write(runner.REVIEW, encode(review | {"expires_at": (utc_now() + timedelta(hours=3)).isoformat()}))
        print(digest(runner.REVIEW.read_bytes()))
        return
    exact = args.first_review
    if runner.RUN.exists() or digest(runner.REVIEW.read_bytes()) != exact:
        raise ValueError("requires an exact unstarted first review")
    write(runner.APPROVAL, encode({"approved": True, "review_sha256": exact}))
    write(TARGET / "first-attempt-authority.json", encode({
        "review_sha256": exact, "standing_authority": str(AUTHORITY.relative_to(ROOT)), "first_attempt": True,
    }))
    try:
        raise SystemExit(0 if await runner.run(exact) else 1)
    finally:
        if runner.RUN.exists() and observations:
            write(runner.RUN / "observations.json", encode(observations))


if __name__ == "__main__":
    asyncio.run(main())
