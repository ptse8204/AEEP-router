"""Freeze an EOS collection audit and seven precise reference diagnostics."""

import argparse
import asyncio
from datetime import timedelta
from pathlib import Path

import check_eos_protected_pair as eos
import check_locify_source_wheels as journal
from stage_repository_transport import ROOT, WORK, encode, write

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now

NAME = "c13-eos-protected-diagnostic-20261119"
TARGET = WORK / NAME
REVIEW = TARGET / "operation-review.json"
ATTEMPT = eos.TARGET / "execution"
ACTUAL_SOURCE = Path(eos.binding.aeep.__file__).resolve().parents[2]


def configuration():
    native = journal.doc(eos.native.TARGET / "result.json")
    observer, env, (case,) = eos.definition(native)
    old = journal.doc(ATTEMPT / "result.json")
    observation, = journal.doc(ATTEMPT / "observations.json")
    statuses = observation["required_statuses"]
    failed = sorted(name for name, status in statuses.items() if status == "FAILED")
    missing = sorted(name for name, status in statuses.items() if status == "MISSING")
    if old["verified"] or len(failed) != 7 or len(missing) != 60 or any("]" in name for name in missing):
        raise ValueError("retained exact diagnostic scope changed")
    argv = list(observer.config["argv"])
    program = argv[-1]
    old = '        tail = base64.b64encode(log.read_bytes()[-8192:] if child.returncode else b\'\').decode(\'ascii\')'
    redaction = """        sites = []
        if child.returncode:
            for line in log.read_text(errors='replace').splitlines():
                found = re.fullmatch(r'.*?(tests/[A-Za-z0-9_/.-]+\\.py):(\\d{1,6}): ([A-Za-z][A-Za-z_0-9]{0,80})(?::.*)?', line)
                if found:
                    sites.append({'file': found[1], 'line': int(found[2]), 'category': found[3]})
        tail = base64.b64encode(json.dumps(sites[:50], separators=(',', ':')).encode()).decode('ascii')"""
    if program.count("OPERATOR_REVIEW = False") != 1 or program.count(old) != 1:
        raise ValueError("approved native observer source drifted")
    argv[-1] = program.replace("OPERATOR_REVIEW = False", "OPERATOR_REVIEW = True").replace(old, redaction)
    compile(argv[-1], "<protected EOS diagnostic>", "exec")
    observer = observer.model_copy(update={"config": dict(observer.config, argv=argv)})
    return observer, env, case, failed, missing


async def definitions():
    spec, env, case, failed, missing = configuration()
    expected = eos.runner.expected_statuses(case["truth"], "reference")
    containers = ContainerExecutor(env)
    launches = {}

    async def project(payload):
        for role, candidate in (
            ("collect", dict(payload, collect_only=True)),
            ("failure-sites", dict(payload, test_paths=failed)),
        ):
            action = eos.runner.context(spec, f"{NAME}:{role}", candidate)
            argv, owned = containers.command(action)
            expected_mount = f"type=bind,src={eos.VERIFIED_SOURCE / 'src'},dst={eos.VERIFIED_SOURCE / 'src'},readonly"
            if (argv[argv.index("--network") + 1] != "none"
                    or argv[argv.index("--user") + 1] != "65534:65534"
                    or {arg for arg in argv if arg.startswith("type=bind,")} != {expected_mount}):
                raise ValueError("diagnostic launch isolation changed")
            launches[role] = {"argv_sha256": content_digest({"argv": argv}),
                "payload_sha256": content_digest(candidate), "archive_sha256": payload["archive_sha256"],
                "container": owned, "selectors": candidate["test_paths"]}
        # Exercise the ordinary payload builder. This first-party reply creates
        # no execution evidence and the CLI never submits it as a case grade.
        return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
            "statuses": expected, "exit_code": 0}

    projected = await grade_suite_output(case["input"], case["truth"], case["roles"]["reference"], project)
    if not projected.valid or len(launches) != 2:
        raise ValueError("diagnostic payload rehearsal failed")
    return spec, env, launches, failed, missing


async def prepare():
    if REVIEW.exists():
        raise ValueError("exact correction review already exists")
    if ACTUAL_SOURCE != eos.VERIFIED_SOURCE:
        raise ValueError("requires frozen source projection")
    observer, env, launches, failed, missing = await definitions()
    files = [Path(__file__), Path(eos.__file__), Path(eos.binding.__file__), Path(eos.runner.__file__),
             ATTEMPT / "ledger.json", ATTEMPT / "result.json", ATTEMPT / "observations.json",
             eos.TARGET / "operation-review.json", eos.native.TARGET / "result.json"]
    record = {
        "schema_version": "aeep.c13.eos-protected-diagnostic-review.v1",
        "source_digest": verification_source_digest(eos.VERIFIED_SOURCE),
        "bindings": {str(path.relative_to(ROOT)): journal.fingerprint(path) for path in files},
        "observer_digest": content_digest(observer),
        "environment": env.model_dump(mode="json"),
        "launches": launches, "unmatched_publisher_ids": missing, "failed_test_ids": failed,
        "diagnose": "Match an unclosed publisher ID only when exactly one complete native ID shares its prefix.",
        "retention": "Protected identities, statuses, and test filename, line, and exception category only.",
        "no_grade": True, "original_roles": 0, "models": 0, "cash_usd": 0,
        "downloads": 0, "builds": 0, "remove_existing_resources": False, "automatic_retries": 0,
        "limits": {"operations": 2, "reserved_seconds": 190},
        "minimum_free_bytes": 52 * 2**30,
        "require_operator_approval_for_repeat": True,
        "expires_at": (utc_now() + timedelta(days=3)).isoformat(),
    }
    write(REVIEW, encode(record))
    print(journal.fingerprint(REVIEW))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", required=True)
    parser.parse_args()
    asyncio.run(prepare())


if __name__ == "__main__":
    main()
