"""No package installation: exercise ownership and recovery with installer doubles."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import stack


class SetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.runtime = self.root / "new-parent" / "runtime"
        self.selected = stack.manifest()

    def state(self):
        return json.loads((self.runtime / "installation-state.json").read_text())

    def test_space_failure_has_no_directory_or_installer_effects(self):
        with patch("shutil.disk_usage", return_value=SimpleNamespace(free=49 * 1024**3)), patch.object(stack.venv, "EnvBuilder") as builder:
            with self.assertRaisesRegex(ValueError, "50 GiB"):
                stack.setup(self.runtime, self.selected)
            builder.assert_not_called()
        self.assertFalse(self.runtime.parent.exists())

    def test_success_records_pins_and_uses_a_minimal_pip_environment(self):
        states = []

        def create(path):
            self.assertEqual(path, self.runtime)
            states.append(self.state()["status"])

        def install(argv, **kwargs):
            states.append(self.state()["status"])
            self.assertIn("-I", argv)
            self.assertEqual(kwargs["env"], {"PATH": os.defpath, "HOME": str(self.runtime),
                                           "PYTHONNOUSERSITE": "1", "PIP_CONFIG_FILE": os.devnull, "LC_ALL": "en_US.UTF-8"})
            if "ensurepip" in argv:
                return "synthetic bootstrap output\n"
            self.assertIn("--require-hashes", argv)
            self.assertIn("--only-binary=:all:", argv)
            self.assertIn("--no-deps", argv)
            self.assertIn("--no-cache-dir", argv)
            self.assertIn("--report", argv)
            self.assertEqual(argv[argv.index("--index-url") + 1], "https://pypi.org/simple")
            return "synthetic installer output\n"

        with patch.object(stack.venv, "EnvBuilder") as builder, patch.object(stack, "command", side_effect=install), patch.object(stack, "verify_runtime", return_value={"versions": {"fixture": "1"}}):
            builder.return_value.create.side_effect = create
            stack.setup(self.runtime, self.selected)
            builder.assert_called_once_with(with_pip=False)
        self.assertEqual(states, ["creating", "bootstrapping", "installing"])
        self.assertEqual(self.state()["status"], "installed")
        self.assertEqual(self.state()["lock_sha256"], self.selected["lock_sha256"])
        self.assertEqual(self.state()["packages_sha256"], self.selected["packages_sha256"])
        self.assertFalse(self.state()["automatic_retry"])
        self.assertEqual(self.runtime.stat().st_mode & 0o777, 0o700)
        with self.assertRaisesRegex(ValueError, "preserved"):
            stack.setup(self.runtime, self.selected)

    def test_venv_failure_and_interrupt_retain_failed_ownership_without_running_pip(self):
        for error in (ValueError("synthetic failure"), KeyboardInterrupt()):
            self.runtime = self.root / type(error).__name__
            with self.subTest(error=type(error).__name__), patch.object(stack.venv, "EnvBuilder") as builder, patch.object(stack, "command") as command:
                builder.return_value.create.side_effect = error
                with self.assertRaises(type(error)):
                    stack.setup(self.runtime, self.selected)
                command.assert_not_called()
            self.assertEqual(self.state()["status"], "failed")
            with self.assertRaisesRegex(ValueError, "preserved"):
                stack.setup(self.runtime, self.selected)

    def test_bootstrap_pip_or_inventory_failure_preserves_partial_runtime(self):
        for failure in ("bootstrap", "install", "verify_runtime"):
            self.runtime = self.root / failure
            with self.subTest(failure=failure), patch.object(stack.venv, "EnvBuilder"), patch.object(stack, "command", return_value="synthetic") as install, patch.object(stack, "verify_runtime", return_value={"versions": {}}) as verify:
                def fail_at_stage(argv, failure=failure, **_):
                    if failure == ("bootstrap" if "ensurepip" in argv else "install"):
                        raise ValueError("synthetic")
                    return "synthetic"
                install.side_effect = fail_at_stage
                if failure == "verify_runtime":
                    verify.side_effect = ValueError("synthetic")
                with self.assertRaises(ValueError):
                    stack.setup(self.runtime, self.selected)
            self.assertEqual(self.state()["status"], "failed")
            self.assertFalse((self.runtime / "aeep-stack.json").exists())

    def test_concurrent_journal_edit_is_preserved(self):
        def edit(_):
            (self.runtime / "installation-state.json").write_text('{"operator_note":"preserve"}\n')

        with patch.object(stack.venv, "EnvBuilder") as builder, patch.object(stack, "command") as install:
            builder.return_value.create.side_effect = edit
            with self.assertRaisesRegex(ValueError, "journal changed"):
                stack.setup(self.runtime, self.selected)
            install.assert_not_called()
        self.assertEqual(self.state(), {"operator_note": "preserve"})

    def test_linked_and_codex_paths_are_refused_before_effects(self):
        linked = self.root / "linked"
        linked.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "preserved"):
            stack.setup(linked, self.selected)
        self.assertFalse(self.runtime.exists())
        protected = self.root / ".codex" / "runtime"
        with self.assertRaisesRegex(ValueError, "outside Codex"):
            stack.setup(protected, self.selected)
        self.assertFalse(protected.parent.exists())
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root / "protected-state")}), self.assertRaisesRegex(ValueError, "outside Codex"):
            stack.setup(self.root / "protected-state" / "runtime", self.selected)
        self.assertFalse((self.root / "protected-state").exists())


if __name__ == "__main__":
    unittest.main()
