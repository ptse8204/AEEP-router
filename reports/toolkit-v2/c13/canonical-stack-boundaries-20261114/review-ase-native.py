"""Prepare and run only a reviewed native boundary test for agent-skill-eval."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import runpy
from pathlib import Path

from aeep.assessment.scheduling import SchedulerDefinition
from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
PAIR = HERE.parent / "canonical-stack-receipts-20261114"
DRIVER = PAIR / "run-boundary-repeat.py"
PROFILE_PATH = "scheduler-native-study.sb"
GIT_PATH = "git"


def load_driver():
    spec = importlib.util.spec_from_file_location("reviewed_pair", DRIVER)
    assert spec and spec.loader
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def replace_workspace(raw, original, workspace):
    binding = f"WORKSPACE=Path('{original}')"
    if raw.count(binding) != 1:
        raise ValueError("restricted Git wrapper has no unique historical workspace binding")
    return raw.replace(binding, f"WORKSPACE=Path({str(workspace)!r})")


def preflight(driver, review):
    driver.check_conditions(review)
    driver.checked_file(review["native_driver"])
    driver.checked_file(review["original_review"])
    driver.checked_file(review["original_result"])
    entry = review["agent_skill_eval"]
    historic = SchedulerDefinition.model_validate(
        driver.helpers.load(driver.checked_file(entry["historical_scheduler"]))
    )
    original_git = driver.checked_file(entry["historical_git"])
    if historic.executable_dependencies[str(original_git)] != entry["historical_git"]["sha256"]:
        raise ValueError("original Git wrapper differs from the historical scheduler")
    git = driver.checked_file(entry["git"])
    workspace = Path(entry["workspace"])
    if git.read_text() != replace_workspace(
        original_git.read_text(), historic.workspace, workspace
    ):
        raise ValueError("copied Git wrapper differs beyond the owned workspace")
    if entry["stdin"]["git"] != str(git):
        raise ValueError("probe must use the scoped Git copy")
    before = driver.checked_file(entry["historical_profile"]).read_text()
    updated_profile = expected_profile(before, historic.workspace, workspace, git)
    if driver.checked_file(entry["current_profile"]).read_text() != updated_profile:
        raise ValueError("sandbox profile differs beyond the reviewed path bindings")
    return driver.agent_skill_eval(review, review["sha256"], apply=False)


def expected_profile(original, old, workspace, git):
    ancestors = (workspace.parent, *workspace.parent.parents)
    metadata = " ".join(f"(literal {json.dumps(str(path))})" for path in ancestors)
    return (
        original.replace(old, str(workspace))
        + f"(allow file-read-metadata {metadata})\n"
        + f"(allow file-read* (literal {json.dumps(str(git))}))\n"
    )


def check_wrapper(git, workspace):
    """Exercise first-party argument validation only. No invocation of Git or the sandbox."""
    prepare = runpy.run_path(str(git))["prepare"]
    argv, env = prepare(["init", "-b", "main"], workspace, {"HOME": str(workspace / "home")})
    assert argv[1:] == ["--no-pager", "init", "-b", "main"]
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null" and not env["GIT_ALLOW_PROTOCOL"]
    for args, directory in (
        (["init", "-b", "main"], workspace.parent),
        (["clone", "https://example.invalid"], workspace),
        (["config", "credential.helper", "unsafe"], workspace),
    ):
        try:
            prepare(args, directory, {})
        except ValueError:
            continue
        raise RuntimeError("Git boundary accepted an unreviewed location or command")
    return 4


def prepare(driver, directory):
    pin, load, save = driver.helpers.pin, driver.helpers.load, driver.helpers.save
    directory.mkdir(mode=0o700)
    original_review = PAIR / "boundary-review.json"
    original_result = HERE / "boundary-result.json"
    previous = load(original_result)
    if not previous["scanner"]["passed"] or previous["agent_skill_eval"]["passed"]:
        raise ValueError("repeat applies only to the terminal failed native check")
    scope = load(original_review)
    old_entry = scope["agent_skill_eval"]
    source = verification_source_digest(driver.ROOT)
    if scope["implementation_source"] != source:
        raise ValueError("coordinator changed since the reviewed pair")
    definition = SchedulerDefinition.model_validate(
        load(Path(old_entry["historical_scheduler"]["path"]))
    )
    original_git = driver.checked_file(old_entry["git"])
    workspace = directory / "ase-native-probe"
    workspace.mkdir(mode=0o700)
    for name in ("home", "tmp", "candidate", "responses"):
        (workspace / name).mkdir(mode=0o700)
    git = directory / GIT_PATH
    git.write_text(replace_workspace(original_git.read_text(), definition.workspace, workspace))
    git.chmod(0o500)
    controls = check_wrapper(git, workspace)
    profile = directory / PROFILE_PATH
    profile.write_text(
        expected_profile(
            driver.checked_file(old_entry["historical_profile"]).read_text(),
            definition.workspace,
            workspace,
            git,
        )
    )
    outside = directory / "outside-read-canary.txt"
    outside.write_bytes(driver.checked_file(old_entry["outside_canary"]).read_bytes())
    request = old_entry["request"]
    operation = old_entry["operation_id"] + ":git-binding"
    with driver.ReceiptStore(old_entry["database"], read_only=True) as store:
        repo = driver.AssessmentRepository(store)
        assert (
            repo.get("operation_measurement", old_entry["operation_id"])["stage"]
            == "ase_current_native_boundary"
        )
        baseline = driver.helpers.debit_baseline(
            repo, request["authorization_id"], plan_id=request["plan_id"]
        )
    entry = old_entry | {
        "baseline": baseline,
        "operation_id": operation,
        "historical_git": pin(original_git),
        "git": pin(git),
        "workspace": str(workspace),
        "workspace_tree_sha256": driver.snapshot(workspace),
        "current_profile": pin(profile),
        "command": [*old_entry["command"][:2], str(profile), *old_entry["command"][3:]],
        "environment": old_entry["environment"]
        | {
            "HOME": str(workspace / "home"),
            "TMPDIR": str(workspace / "tmp"),
        },
        "outside_canary": pin(outside),
        "stdin": {
            "outside": str(outside),
            "outside_write": str(directory / "denied-write"),
            "git": str(git),
        },
    }
    review = {
        "schema_version": "aeep.operator.toolkit-ase-native-repeat.v1",
        "purpose": "Validate the current sandbox launcher against the retained ASE scheduler policy.",
        "implementation_source": source,
        "expires_at": scope["expires_at"],
        "original_review": pin(original_review),
        "original_result": pin(original_result),
        "driver": pin(DRIVER),
        "native_driver": pin(Path(__file__).resolve()),
        "agent_skill_eval": entry,
        "prior_attempt": previous["agent_skill_eval"]["measurement_ref"],
        "maximum_additional_operations": 1,
        "maximum_reserved_seconds": 35,
        "model_turns": 0,
        "maximum_cash_usd": 0,
        "exclusions": [
            "Cisco replay",
            "model execution",
            "upstream SDK execution",
            "installations",
            "downloads",
            "credentials",
            "provider access",
            "existing resource removal",
            "retry",
            "comparison",
            "release",
            "admission",
        ],
        "preparation_controls": {"restricted_git_argument_and_workspace_checks": controls},
    }
    file = save(directory / "operation-review.json", review)
    return file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute-approved")
    args = parser.parse_args()
    driver = load_driver()
    file = prepare(driver, args.path.resolve()) if args.prepare else args.path.resolve()
    review = driver.helpers.load(file)
    ref = hashlib.sha256(file.read_bytes()).hexdigest()
    assert review["schema_version"] == "aeep.operator.toolkit-ase-native-repeat.v1"
    assert review["maximum_additional_operations"] == 1 and review["maximum_reserved_seconds"] == 35
    review["sha256"] = ref
    checks = preflight(driver, review)
    if args.execute_approved is None:
        print(
            json.dumps(
                {
                    "path": str(file),
                    "review_sha256": ref,
                    "preflight": checks,
                    "preparation_controls": review["preparation_controls"],
                    "execution": False,
                },
                indent=2,
            )
        )
        return
    approval = driver.helpers.load(file.with_name("operator-approval.json"))
    assert (
        args.execute_approved == ref == approval["review_sha256"] and approval["approved"] is True
    )
    driver.helpers.save(file.with_name("started.json"), {"review_sha256": ref})
    result = driver.agent_skill_eval(review, ref, apply=True)
    driver.helpers.save(file.with_name("result.json"), result)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
