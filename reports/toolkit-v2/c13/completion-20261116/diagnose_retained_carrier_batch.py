"""Observe protected collection failures without retaining upstream log text."""

import argparse
import asyncio
import json
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import check_retained_carrier_batch as batch
from stage_repository_transport import digest, read

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

runner = batch.runner
WORK = batch.WORK
DIAGNOSTIC = r"""
        assert log.stat().st_size <= 500_000
        classes = set()
        allowed = {
            'AssertionError', 'ImportError', 'ModuleNotFoundError', 'PackageNotFoundError',
            'RuntimeError', 'SyntaxError', 'TypeError', 'ValueError', 'AttributeError',
            'PermissionError', 'OSError', 'FileNotFoundError', 'ConftestImportFailure',
            'NameError', 'KeyError', 'SystemExit', 'UnboundLocalError',
        }
        for line in log.read_text(errors='replace').splitlines():
            for found in re.findall(r'(?:^|[\s.])([A-Za-z_]+Error|ConftestImportFailure|SystemExit|NameError)(?=[:\s]|$)', line):
                if found in allowed:
                    classes.add(found)
        return {
            'exit_code': child.returncode, 'classes': sorted(classes),
            'collection_emitted': events.is_file() and not events.is_symlink(),
        }
"""
STARTUP = """
        boot = boot[:boot.index(';os.chdir(')] + (';import skelebot' if KEY == 'skelebot' else '')
        audit = '''
import json,sys,traceback
try:
    exec(compile(sys.argv[1], '<case-startup>', 'exec'), globals())
except BaseException as exc:
    sources = {'/tmp/aeep-repository-native-v6/': 'source', sys.argv[2] + '/': 'dependency'}
    sites = []
    for frame in traceback.extract_tb(exc.__traceback__):
        for prefix, kind in sources.items():
            if frame.filename.startswith(prefix):
                path = frame.filename[len(prefix):]
                if path.isascii() and path.endswith('.py') and all(c.isalnum() or c in '/._-' for c in path):
                    sites.append([kind,path,frame.lineno])
    print(json.dumps({'ok':False,'class':type(exc).__name__,'sites':sites[-12:]}))
else:
    print(json.dumps({'ok':True,'class':None,'sites':[]}))
'''
        startup = subprocess.run([sys.executable,'-B','-c',audit,boot,SUPPORT],cwd=root,
            env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(root),
                 'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'},
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if startup.returncode or len(startup.stdout)>10000:
            return {'ok':False,'class':'ChildProcessError','sites':[]}
        return json.loads(startup.stdout.decode().splitlines()[-1])
"""


async def plan(key, expires, *, next_step=False, startup=False):
    batch.assets.SUPPORT = WORK / "support"
    batch.assets.WHEELS = WORK / "wheels"
    case_dir = WORK / key
    parent = case_dir / "operation-review.json"
    attempt = case_dir / "execution"
    result = runner.get(attempt / "result.json")
    ledger = runner.get(attempt / "ledger.json")
    (observation,) = result["observations"]
    (charged,) = ledger["operations"]
    if (
        result["verified"]
        or observation["contract_matched"]
        or charged["elapsed_seconds"] is None
        or charged["operation_id"] != observation["operation"]
        or not charged["operation_id"].endswith(":reference")
        or result["review_sha256"] != file_digest(parent)
    ):
        raise ValueError("reference attempt is not the expected settled failure")
    original = runner.get(parent)
    pins = original["package_pins"]
    projected = batch.import_only_pins(key, pins)
    inventory = batch.assets.support_check(key, projected)
    if (
        digest(json.dumps(inventory, sort_keys=True).encode())
        != original["read_only_import_tree_sha256"]
    ):
        raise ValueError("retained runtime changed")
    faults, case = batch.cases()[key]
    batch.configure(key, case, faults, pins)
    spec, env, _ = runner.definitions()
    if (
        content_digest(spec) != original["observer_fingerprint"]
        or env.model_dump(mode="json") != original["environment"]
    ):
        raise ValueError("diagnostic does not start from the failed environment")
    payload = {}
    expected = runner.expected_statuses(case["truth"], "reference")

    async def capture(body):
        payload.update(body)
        return {k: body[k] for k in ("archive_sha256", "python", "pytest")} | {
            "exit_code": 0,
            "statuses": expected,
        }

    simulated = await grade_suite_output(
        case["input"], case["truth"], case["roles"]["reference"], capture
    )
    if not simulated.valid or content_digest(payload) != original["launches"][0]["payload_sha256"]:
        raise ValueError("protected payload changed")
    parent_result = attempt / "result.json"
    parent_ledger = attempt / "ledger.json"
    extra_allowance = 0
    if next_step:
        if key == "skelebot":
            import complete_skelebot_metadata_pair as fixed

            parent = fixed.CORRECTION / "review-preserve-expiry.json"
            correction = runner.get(parent)
            parent_result = fixed.CORRECTION / "result.json"
            parent_ledger = fixed.CORRECTION / "ledger.json"
            latest = runner.get(parent_result)
            if latest["review_sha256"] != file_digest(parent) or latest["verified"]:
                raise ValueError("the corrected reference is not a settled failure")
            reconstructed, _, _, actions, _ = await fixed.plan(correction["expires_at"])
            if reconstructed != correction:
                raise ValueError("metadata launch changed")
            action, *_ = actions
            spec = action.spec
            env = env.model_copy(
                update={"read_only_roots": [*env.read_only_roots, str(fixed.META)]}
            )
        else:
            parent_result = case_dir / "diagnostic" / "result.json"
            parent_ledger = case_dir / "diagnostic" / "ledger.json"
            observed = runner.get(parent_result)
            if observed["observations"] != {
                "exit_code": 1,
                "classes": [],
                "collection_emitted": False,
            }:
                raise ValueError("AnyIO did not stop before collection as expected")
            extra_allowance = 1
        ledger = runner.get(parent_ledger)
        if any(item["elapsed_seconds"] is None for item in ledger["operations"]):
            raise ValueError("previous operations did not settle")
    if startup:
        parent_result = case_dir / "diagnostic-followup" / "result.json"
        parent_ledger = case_dir / "diagnostic-followup" / "ledger.json"
        ledger = runner.get(parent_ledger)
        if (
            any(item["elapsed_seconds"] is None for item in ledger["operations"])
            or runner.get(parent_result)["grade"]
        ):
            raise ValueError("closed diagnostic evidence changed")
        extra_allowance = 1
    argv = list(spec.config["argv"])
    text = argv[-1]
    point = "        assert log.stat().st_size <= 500_000 and events.is_file()"
    if text.count(point) != 1 or text.count("OPERATOR_REVIEW = False") != 1:
        raise ValueError("native observer changed")
    the_end = text.index("\n\n\nif __name__")
    argv[-1] = (
        text[: text.index(point)].replace("OPERATOR_REVIEW = False", "OPERATOR_REVIEW = True")
        + DIAGNOSTIC
        + text[the_end:]
    )
    if startup:
        prefix = argv[-1][: argv[-1].index("        log = root")]
        suffix = argv[-1][argv[-1].index("\n\n\nif __name__") :]
        interpreter = STARTUP.replace("KEY", repr(key)).replace(
            "SUPPORT", repr(str(batch.assets.SUPPORT / key))
        )
        argv[-1] = prefix + interpreter + suffix
    compile(argv[-1], "<protected diagnostic>", "exec")
    diagnostic = spec.model_copy(update={"config": spec.config | {"argv": argv}})
    operation = runner.NAME + (
        ":startup" if startup else ":collect-followup" if next_step else ":collect"
    )
    action = runner.context(diagnostic, operation, payload | {"collect_only": True})
    executor = ContainerExecutor(env)
    command, owner = executor.command(action)
    if (
        command[command.index("--network") + 1] != "none"
        or command[command.index("--user") + 1] != "65534:65534"
        or not {"--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges"}
        <= set(command)
    ):
        raise ValueError("reviewed container boundary was lost")
    return (
        {
            "parent_review": file_digest(parent),
            "parent_result": file_digest(parent_result),
            "parent_ledger": file_digest(parent_ledger),
            "driver_sha256": file_digest(Path(__file__)),
            "case": case["case_id"],
            "argv_sha256": content_digest({"argv": command}),
            "payload_sha256": content_digest(action.request.input),
            "container": owner,
            "operations": 1,
            "reserved_seconds": 50,
            "expires_at": expires,
            "grade": False,
            "collection_only": not startup,
            "startup_only": startup,
            "models": 0,
            "cash_usd": 0,
            "raw_logs_retained": False,
            "provider_disclosure": False,
            "retry": False,
            "additional_budget_operations": extra_allowance,
            "next_step": next_step,
        },
        executor,
        action,
        ledger,
        attempt,
    )


async def execute(key, exact, recipe, executor, action, previous, attempt):
    stage = attempt.parent / (
        "startup"
        if recipe["startup_only"]
        else ("diagnostic-followup" if recipe["next_step"] else "diagnostic")
    )
    if (
        stage.exists()
        or shutil.disk_usage(WORK).free < batch.assets.FLOOR
        or datetime.fromisoformat(recipe["expires_at"]) <= utc_now()
    ):
        raise ValueError("prior diagnostic or insufficient host space")
    owner = recipe["container"]
    if runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$"):
        raise ValueError("diagnostic container already exists")
    operation = action.request.action_id
    with ReceiptStore(attempt / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        grant = AssessmentAuthorization.model_validate(repo.get("authorization", runner.NAME))
        active = repo.current_grant(runner.NAME)
        expected_operations = (
            len(previous["operations"]) + 1 - recipe["additional_budget_operations"]
        )
        if repo.operation_ledger(runner.NAME).model_dump(
            mode="json"
        ) != previous or active.limits != AssessmentLimits(
            max_operations=expected_operations, max_elapsed_seconds=expected_operations * 50
        ):
            raise ValueError("parent grant or charge changed")
        if grant.remote_disclosure or grant.limits.max_cash_usd or grant.limits.max_model_turns:
            raise ValueError("parent grant is wider than the offline diagnostic")
        (old,) = grant.subject_digests
        definition = runner.Scope(review_sha256=exact)
        new = content_digest(definition)
        repo.put("c13_retained_carrier_diagnostic", new, definition)
        budget = None
        if recipe["additional_budget_operations"]:
            prior = None
            if recipe["startup_only"]:
                prior = repo.get(
                    "budget_amendment",
                    runner.NAME
                    + (":metadata-budget" if key == "skelebot" else ":collect-followup:budget"),
                )
            budget = AssessmentBudgetAmendment(
                amendment_id=operation + ":budget",
                authorization_id=runner.NAME,
                authorization_digest=content_digest(grant),
                previous_amendment_digest=content_digest(prior) if prior is not None else None,
                expires_at=active.expires_at,
                limits=AssessmentLimits(
                    max_operations=expected_operations + 1,
                    max_elapsed_seconds=(expected_operations + 1) * 50,
                ),
            )
        repo.approve_bundle(
            AssessmentScopeAmendment(
                amendment_id=operation,
                authorization_id=runner.NAME,
                authorization_digest=content_digest(grant),
                subject_digests=[old],
                recipe_digests=[old],
                environment_digests=[old],
                reviewed_digests=[new],
            ),
            {
                old: repo.get("c13_cached_repository_pair_scope", old),
                new: definition.model_dump(mode="json"),
            },
            budget_amendment=budget,
        )
        request = RecipeMaterializationRequest(
            plan_id=runner.NAME,
            authorization_id=runner.NAME,
            subject_digest=old,
            recipe_digest=old,
            environment_digest=old,
            mapping_digest=old,
            definition_digests=[old, new],
            seed=0,
        )
        stage.mkdir(mode=0o700)
        runner.put(stage / "started.json", {"review_sha256": exact})
        repo.reserve(
            request,
            operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=50),
            stage="protected_collection_diagnostic",
            require_settled_plan=True,
        )
        started, elapsed = utc_now(), time.monotonic()
        try:
            raw = await executor.execute(action)
        finally:
            await executor.close()
        if runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$"):
            raise RuntimeError("container absence could not be verified")
        reply = raw.output
        valid = (
            raw.status.value == "success"
            and isinstance(reply, dict)
            and set(reply) == {"exit_code", "classes", "collection_emitted"}
            and type(reply["exit_code"]) is int
            and type(reply["collection_emitted"]) is bool
            and isinstance(reply["classes"], list)
            and len(reply["classes"]) <= 15
            and all(isinstance(item, str) and item.isalpha() for item in reply["classes"])
        )
        if recipe["startup_only"]:
            valid = (
                raw.status.value == "success"
                and isinstance(reply, dict)
                and set(reply) == {"ok", "class", "sites"}
                and type(reply["ok"]) is bool
                and (
                    reply["class"] is None
                    if reply["ok"]
                    else isinstance(reply["class"], str) and reply["class"].isalpha()
                )
                and isinstance(reply["sites"], list)
                and len(reply["sites"]) <= 12
                and all(
                    isinstance(site, list)
                    and len(site) == 3
                    and site[0] in {"source", "dependency"}
                    and isinstance(site[1], str)
                    and site[1].isascii()
                    and site[1].endswith(".py")
                    and all(c.isalnum() or c in "/._-" for c in site[1])
                    and type(site[2]) is int
                    and site[2] > 0
                    for site in reply["sites"]
                )
            )
        receipt = ExecutionReceipt(
            decision_id=operation,
            action_id=operation,
            capability=action.spec.capability,
            executor_id=action.spec.id,
            executor_kind=action.spec.kind,
            estimated=action.estimate,
            started_at=started,
            ended_at=utc_now(),
            status="success" if valid else "failed",
            execution_success=valid,
            actual_resources=raw.resources,
            error_type=None if valid else raw.error_type or "DIAGNOSTIC_MISMATCH",
            metadata={"container_absent": True, "review_sha256": exact},
        )
        store.save_receipt(receipt)
        repo.finish_operation(
            operation, elapsed_seconds=time.monotonic() - elapsed, resources=raw.resources
        )
        runner.put(
            stage / "result.json",
            {
                "profile": key,
                "receipt_id": receipt.receipt_id,
                "observations": reply if valid else None,
                "infrastructure_error": receipt.error_type,
                "grade": False,
            },
        )
        runner.put(
            stage / "ledger.json", repo.operation_ledger(runner.NAME).model_dump(mode="json")
        )
    return valid


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=batch.PROFILES)
    parser.add_argument("--followup", action="store_true")
    parser.add_argument("--startup", action="store_true")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--execute")
    args = parser.parse_args()
    path = (
        WORK
        / args.profile
        / (
            "startup-review.json"
            if args.startup
            else "diagnostic-followup-review.json"
            if args.followup
            else "diagnostic-review.json"
        )
    )
    old = None if args.prepare else json.loads(read(path, args.execute))
    expires = (utc_now() + timedelta(hours=2)).isoformat() if old is None else old["expires_at"]
    review, *launch = await plan(
        args.profile, expires, next_step=args.followup or args.startup, startup=args.startup
    )
    if args.prepare:
        runner.put(path, review)
        print(file_digest(path))
    else:
        if review != old:
            raise ValueError("diagnostic launch has changed")
        raise SystemExit(not await execute(args.profile, args.execute, review, *launch))


if __name__ == "__main__":
    asyncio.run(main())
