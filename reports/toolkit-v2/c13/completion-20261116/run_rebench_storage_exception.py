"""Run the approved group under its one-use storage exception."""

import argparse
import asyncio
import hashlib
import shutil
from pathlib import Path

import execute_rebench_correction_group as group
from stage_repository_transport import ROOT, encode, write

from aeep.models import utc_now

BASE = "c955cbf68ccfd50159db16213de9d02e38932972f0c5fcb7e5ee73dc07e794f0"
REVIEW = group.TARGET / "storage-exception-review.json"
NET_LIMIT = 2 * 2**30
FLOOR = "STORAGE_EXCEPTION_FLOOR_BYTES"
OUTCOME_PIN = "STORAGE_EXCEPTION_REVIEW_SHA256"


def overlays():
    # Keep the reviewed files byte-for-byte. Apply the exception only inside
    # this process. Every change must match the exact pinned source once.
    return {
        group: [
            ('shutil.disk_usage(ROOT).free < scope["minimum_build_free_bytes"]', f"shutil.disk_usage(ROOT).free < {FLOOR}", 1),
            ('shutil.disk_usage(ROOT).free < scope["minimum_free_bytes"]', f"shutil.disk_usage(ROOT).free < {FLOOR}", 2),
            ("if shutil.disk_usage(ROOT).free < 53 * 2**30:", f"if shutil.disk_usage(ROOT).free < {FLOOR}:", 1),
            ('raise ValueError("restore 53 GiB usable to start both reviewed branches")',
             'raise ValueError("host storage fell below the one-use exception floor")', 1),
            ('write(TARGET / "started.json", encode({"exact_review": exact}))',
             f'write(TARGET / "started.json", encode({{"exact_review": exact, "storage_exception": {OUTCOME_PIN}}}))\n'
             f"    exact = {OUTCOME_PIN}", 1),
        ],
        group.journal: [
            ("shutil.disk_usage(ROOT).free < 50 * 2**30", f"shutil.disk_usage(ROOT).free < {FLOOR}", 1),
        ],
        group.locify.locify.runner: [
            ("shutil.disk_usage(WORK).free < 52 * 1024**3", f"shutil.disk_usage(WORK).free < {FLOOR}", 2),
        ],
    }


def patched_drivers():
    review = group.journal.doc(group.GROUP)
    result = {}
    for module, replacements in overlays().items():
        path = Path(module.__file__).resolve()
        relative = str(path.relative_to(ROOT))
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != review["pins"][relative]:
            raise ValueError(f"approved driver bytes changed at {relative}")
        source = original.decode()
        for before, after, count in replacements:
            if source.count(before) != count:
                raise ValueError(f"unexpected storage guard layout at {relative}")
            source = source.replace(before, after)
        result[module] = source
    return result


async def prepare():
    group.preflight(BASE, live=True)
    _, _, observed, *_ = await group.eos.definitions()
    if observed != group.journal.doc(group.eos.REVIEW)["launches"]:
        raise ValueError("protected EOS commands changed")
    drivers = patched_drivers()
    for module, source in drivers.items():
        compile(source, module.__file__, "exec")
    baseline = shutil.disk_usage(ROOT).free
    if baseline <= NET_LIMIT:
        raise ValueError("usable space cannot accommodate the bounded build")
    record = {
        "schema_version": "aeep.c13.rebench-storage-exception.v1",
        "base_review_sha256": BASE,
        "base_approval_sha256": group.journal.fingerprint(group.APPROVAL),
        "operator_direction": "Continue with the current usable space despite the usual 50 GiB requirement.",
        "observed_at": utc_now().isoformat(),
        "measured_baseline_free_bytes": baseline,
        "minimum_free_bytes": baseline - NET_LIMIT,
        "maximum_net_space_drop_bytes": NET_LIMIT,
        "capacity_basis": "One local COPY-only layer and existing retained runtimes. No pulls, installs or cleanup.",
        "driver_sha256": group.journal.fingerprint(Path(__file__)),
        "patched_source_sha256": {str(Path(module.__file__).relative_to(ROOT)): hashlib.sha256(source.encode()).hexdigest()
                                  for module, source in drivers.items()},
    }
    with REVIEW.open("xb") as stream:
        stream.write(encode(record))
    print(group.journal.fingerprint(REVIEW), flush=True)


async def execute(exact):
    group.preflight(BASE, live=True)
    record = group.journal.doc(REVIEW)
    if (group.journal.fingerprint(REVIEW) != exact or record["base_review_sha256"] != BASE
            or record["base_approval_sha256"] != group.journal.fingerprint(group.APPROVAL)
            or record["driver_sha256"] != group.journal.fingerprint(Path(__file__))
            or record["minimum_free_bytes"] != record["measured_baseline_free_bytes"] - NET_LIMIT
            or record["minimum_free_bytes"] <= 0):
        raise ValueError("one-use storage review or its operator approval drifted")
    drivers = patched_drivers()
    if {str(Path(module.__file__).relative_to(ROOT)): hashlib.sha256(source.encode()).hexdigest()
        for module, source in drivers.items()} != record["patched_source_sha256"]:
        raise ValueError("amended driver bytes changed")
    for module, source in drivers.items():
        module.__dict__[FLOOR] = record["minimum_free_bytes"]
        module.__dict__[OUTCOME_PIN] = exact
        exec(compile(source, module.__file__, "exec"), module.__dict__)
    try:
        await group.execute(BASE)
    finally:
        write(group.TARGET / "storage-exception-observation.json", encode({
            "storage_exception_sha256": exact,
            "observed_free_bytes": shutil.disk_usage(ROOT).free,
            "base_review_sha256": BASE,
        }))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--prepare", action="store_true")
    command.add_argument("--execute")
    args = parser.parse_args()
    asyncio.run(prepare() if args.prepare else execute(args.execute))


if __name__ == "__main__":
    main()
