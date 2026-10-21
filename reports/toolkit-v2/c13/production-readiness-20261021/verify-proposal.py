"""Verify proposed limits, frozen evidence and local documentation; no execution."""
import hashlib
import json
import math
import runpy
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from aeep.assessment.verification import verification_source_digest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BASE = "b63fb6d"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    proposal = json.loads((OUT / "production-resource-proposal.json").read_text())
    assert proposal["status"] == "RECOMMENDED_NOT_ACCEPTED_OR_EXECUTED"
    assert verification_source_digest(ROOT) == proposal["source_digest"]
    targets = proposal["targets"]
    for value in targets.values():
        if isinstance(value, (int, float)):
            assert math.isfinite(value) and value >= 0
    assert targets["minimum_host_free_during_bytes"] == 50 * 1024**3
    assert targets["minimum_host_free_before_bytes"] > targets["minimum_host_free_during_bytes"]
    assert targets["minimum_available_host_memory_before_bytes"] >= targets["minimum_available_host_memory_during_bytes"] + targets["assessment_incremental_host_memory_max_bytes"]
    assert targets["proxy_memory_bytes_existing"] == targets["proxy_memory_swap_bytes_existing"] == 512 * 1024**2
    assert targets["cash_authorization_usd"] == "0"
    assert targets["model_task_seconds_max_existing"] == 102
    future = proposal["prospective_qualification"]
    assert sum(future["core_counts"].values()) == future["core_valid_transactions"] == 30
    assert future["core_valid_transactions"] + sum(future["warmups"].values()) + future["boundary_negative_checks_max"] == future["core_max_cli_invocations_including_warmup_and_negative"] == 42
    assert future["resource_only_cases"] * 2 == future["resource_only_model_turns_max"] == 12
    assert not future["model_execution_authorized"] and not future["private_reinstallation_authorized"] and not future["old_comparison_replay"]
    sources = json.loads((OUT / "sources.json").read_text())
    for path, digest in sources["local_inputs"].items():
        assert sha(ROOT / path) == digest, path
    original = ROOT / "reports/toolkit-v2/c07/capture-explicit-profile-20261021/positive-operation-review.json"
    assert sha(original) == "ba27e521798f450581d66ba963bd9a764799474af1c64c137a83e00eb36fd91e"
    for path, digest in json.loads(original.read_text())["exact_driver_inputs"].items():
        assert sha(ROOT / path) == digest, path
    exercise = ROOT / "reports/toolkit-v2/c13/human-comprehension/editing-comparison-exercise.json"
    for path, digest in json.loads(exercise.read_text())["presented_files"].items():
        assert sha(ROOT / path) == digest, path
    control = json.loads((OUT / "control-check-exercise.json").read_text())
    assert control["help_already_supplied"] and control["response"] is None
    for path, digest in control["presented_files"].items():
        assert sha(ROOT / path) == digest, path
    help_checks = json.loads((OUT / "control-command-checks.json").read_text())
    assert help_checks["passed"] and help_checks["models"] == help_checks["state_changes"] == 0
    assert len(help_checks["checks"]) == 2 and all(check["exit_code"] == 0 for check in help_checks["checks"])

    # Reuse the earlier read-only Markdown helpers without calling its main/output path.
    helpers = runpy.run_path(str(ROOT / "reports/toolkit-v2/c07/capture-explicit-profile-20261021/verify-final-record.py"))
    names = set()
    for args in (["diff", BASE, "--name-only", "-z"], ["ls-files", "--others", "--exclude-standard", "-z"]):
        names.update(path.decode() for path in subprocess.check_output(["git", *args], cwd=ROOT).split(b"\0") if path)
    markdown = [ROOT / path for path in sorted(names) if path.endswith(".md")]
    checked = 0
    for path in markdown:
        for block in helpers["MD"].parse(path.read_text()):
            for token in block.children or []:
                value = token.attrGet("href") if token.type == "link_open" else token.attrGet("src") if token.type == "image" else None
                if value is None:
                    continue
                parsed = urlsplit(value)
                if parsed.scheme or parsed.netloc:
                    continue
                dest = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
                assert dest.exists(), (path, value)
                if parsed.fragment and dest.suffix == ".md":
                    assert unquote(parsed.fragment) in helpers["heading_ids"](dest), (path, value)
                checked += 1
    result = {
        "passed": True,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_digest_unchanged": proposal["source_digest"],
        "proposed_not_authorized_or_executed": True,
        "original_positive_execution_input_pins_unchanged": 8,
        "original_human_presented_files_unchanged": 5,
        "new_control_exercise_file_pins_unchanged": len(control["presented_files"]),
        "two_help_commands_verified_without_effects": True,
        "actual_participant_control_response": "pending; automation cannot supply it",
        "changed_markdown_files": len(markdown),
        "local_targets_and_markdown_anchors_checked": checked,
        "markdown_sha256": {str(path.relative_to(ROOT)): sha(path) for path in markdown},
        "limits": "Local structural checks, not Lychee or visual/human/resource acceptance. No models, installations, Docker or canonical grant mutation.",
    }
    (OUT / "verification-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "markdown_sha256"}))


if __name__ == "__main__":
    main()
