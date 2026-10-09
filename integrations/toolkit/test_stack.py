"""Exercise the development bridge's evidence and process failure boundaries."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import stack


class StackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subject = hashlib.sha256(b"SKILL.md\0" + (stack.BASE / "fixtures/format-json/SKILL.md").read_bytes() + b"\0").hexdigest()
        for case in ("format", "adjacent"):
            for arm in ("without_skill", "with_skill"):
                directory = self.root / f"eval-{case}" / "fake" / arm
                (directory / "outputs").mkdir(parents=True)
                passed = case == "adjacent" or arm == "with_skill"
                output = "baseline output" if case == "adjacent" else "formatted-json-ok" if passed else "baseline"
                (directory / "outputs/output.txt").write_text(output)
                data = {
                    "run_meta.json": {"eval_id": case, "agent": "fake", "harness_version": "0.7.0",
                                      "model": None, "with_skill": arm == "with_skill", "skill_hash": subject},
                    "timing.json": {"exit_code": 0, "timed_out": False, "retries": 0},
                    "grading.json": {"assertion_results": [{"passed": passed, "skipped": False, "method": "deterministic"}]},
                    "trajectory.json": [{"event": "skill_installed"}] if arm == "with_skill" else [],
                }
                for name, value in data.items():
                    (directory / name).write_text(json.dumps(value))

    def change(self, name, change):
        path = self.root / "eval-format/fake/with_skill" / name
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def test_both_arms_are_verified_without_claiming_model_metrics(self):
        rows = stack.collect(self.root)
        self.assertEqual([row["verified"] for row in rows], [False, True, True, True])
        self.assertTrue(all(row["model_tokens"] is None and row["actual_cash"] is None for row in rows))

    def test_empty_zero_exit_upstream_suite_is_not_success(self):
        with tempfile.TemporaryDirectory() as empty, self.assertRaises(FileNotFoundError):
            stack.collect(Path(empty))

    def test_changed_candidate_is_rejected(self):
        self.change("run_meta.json", lambda data: data.update(skill_hash="0" * 64))
        with self.assertRaisesRegex(ValueError, "pinned"):
            stack.collect(self.root)

    def test_wrong_host_and_incomplete_trials_are_rejected(self):
        for file, changes in (("run_meta.json", {"agent": "codex"}),
                              ("timing.json", {"timed_out": True}),
                              ("timing.json", {"retries": 1})):
            with self.subTest(changes=changes):
                path = self.root / "eval-format/fake/with_skill" / file
                original = path.read_text()
                self.change(file, lambda data, changes=changes: data.update(changes))
                with self.assertRaises(ValueError):
                    stack.collect(self.root)
                path.write_text(original)

    def test_grader_disagreement_is_rejected(self):
        self.change("grading.json", lambda data: data["assertion_results"][0].update(passed=False))
        with self.assertRaisesRegex(ValueError, "disagrees"):
            stack.collect(self.root)

    def test_exposure_mismatch_is_rejected(self):
        self.change("trajectory.json", lambda data: data.clear())
        with self.assertRaisesRegex(ValueError, "exposure"):
            stack.collect(self.root)

    def test_existing_runtime_cannot_be_overwritten(self):
        with self.assertRaisesRegex(ValueError, "preserved"):
            stack.setup(self.root, stack.manifest())

    def test_drifted_fixture_blocks_before_execution(self):
        with patch.object(stack, "digest", return_value="wrong"), self.assertRaisesRegex(ValueError, "changed"):
            stack.manifest()

    def test_package_inventory_is_bound_to_exact_lock(self):
        original = stack.read
        packages = original(stack.BASE / "packages.json")
        packages[0]["version"] = "99.0.0"
        with patch.object(stack, "read", side_effect=lambda path: packages if path.name == "packages.json" else original(path)), self.assertRaisesRegex(ValueError, "wheel lock"):
            stack.manifest()

    def test_unlisted_payload_is_rejected_even_when_upstream_would_not_hash_it(self):
        selected = stack.manifest()
        base = self.root / "source"
        shutil.copytree(stack.BASE / "fixtures", base / "fixtures")
        for extra in ("resources/evals/answer.txt", "resources/.git/config", "extra.txt"):
            with self.subTest(extra=extra), patch.object(stack, "BASE", base):
                path = base / "fixtures/format-json" / extra
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic marker")
                with self.assertRaisesRegex(ValueError, "Unlisted"):
                    stack.fixture_payload(selected)
                path.unlink()
                if (base / "fixtures/format-json/resources").exists():
                    shutil.rmtree(base / "fixtures/format-json/resources")

    def test_fixture_capture_rejects_links_special_files_drift_and_missing_files(self):
        selected = stack.manifest()
        base = self.root / "source"
        shutil.copytree(stack.BASE / "fixtures", base / "fixtures")
        path = base / "fixtures/format-json/SKILL.md"
        original = path.read_bytes()
        with patch.object(stack, "BASE", base):
            captured = stack.fixture_payload(selected)
            self.assertEqual(captured[Path("fixtures/format-json/SKILL.md")], original)
            path.write_text("changed")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                stack.fixture_payload(selected)
            path.unlink()
            with self.assertRaisesRegex(ValueError, "incomplete"):
                stack.fixture_payload(selected)
            other = self.root / "other"
            other.write_bytes(original)
            path.symlink_to(other)
            with self.assertRaisesRegex(ValueError, "linked"):
                stack.fixture_payload(selected)
            path.unlink()
            os.link(other, path)
            with self.assertRaisesRegex(ValueError, "hard links"):
                stack.fixture_payload(selected)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaisesRegex(ValueError, "regular file"):
                stack.fixture_payload(selected)

    def test_fixture_roots_and_declared_paths_are_bounded(self):
        selected = stack.manifest()
        for name in ("", "/tmp/fixture", "fixtures/../other", "other/file"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Invalid"):
                stack.fixture_payload({**selected, "fixtures": {name: "a" * 64}})
        base = self.root / "source"
        base.mkdir()
        (base / "fixtures").symlink_to(stack.BASE / "fixtures", target_is_directory=True)
        with patch.object(stack, "BASE", base), self.assertRaisesRegex(ValueError, "ordinary directory"):
            stack.fixture_payload(selected)

    def test_timeout_terminates_command(self):
        with self.assertRaisesRegex(ValueError, "timed out"):
            stack.command([sys.executable, "-c", "import time; time.sleep(10)"], cwd=self.root, timeout=0.1)

    def test_report_marks_fixture_metrics_unavailable_and_hashes_outputs(self):
        output = self.root / "report"
        output.mkdir()
        stack.report(output, stack.manifest(), {"versions": {"agent-skill-eval": "0.7.0"}}, stack.collect(self.root), {})
        self.assertEqual(stack.read(output / "evidence.json")["outcome"], "NOT_ASSESSED")
        self.assertIn("synthetic", (output / "index.html").read_text().lower())
        components = stack.manifest()["recommended_components"]
        self.assertEqual(len(components), 14)
        self.assertIn("GitHub Sponsors", (output / "index.html").read_text())
        self.assertTrue(all(item["preferred_solution"] in (output / "index.html").read_text() for item in components))
        for name, expected in stack.read(output / "artifact-hashes.json").items():
            self.assertEqual(stack.digest(output / name), expected)


if __name__ == "__main__":
    unittest.main()
