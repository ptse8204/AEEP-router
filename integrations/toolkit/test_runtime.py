"""The installed runtime is data during inspection, never an executable probe."""

import hashlib
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime import inspect_runtime

from aeep_toolkit.cli import read_bytes, read_json


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / 'pyvenv.cfg').write_text('version = 3.13.1\ninclude-system-site-packages = false\n')
        self.site = self.root / 'lib/python3.13/site-packages'
        self.site.mkdir(parents=True)
        self.metadata = self.distribution('agent_skill_eval-0.7.0', 'agent-skill-eval', '0.7.0')
        self.source = self.site / 'agent_skill_eval/__init__.py'
        self.source.parent.mkdir()
        self.source.write_text('raise AssertionError("never import this")\n')
        self.stack = {'evaluator': {'source_files': {'agent_skill_eval/__init__.py': hashlib.sha256(self.source.read_bytes()).hexdigest()}}}
        self.packages = [{'name': 'agent-skill-eval', 'version': '0.7.0', 'license': 'MIT', 'sha256': 'a'*64, 'requires_dist': []}]

    def distribution(self, directory, name, version):
        path = self.site / (directory + '.dist-info') / 'METADATA'
        path.parent.mkdir()
        path.write_text(f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\nUntrusted body\n')
        return path

    def inspect(self):
        return inspect_runtime(self.root, self.stack, self.packages)

    def snapshot(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def test_inspection_never_executes_runtime_or_changes_it(self):
        (self.root / 'bin').mkdir()
        (self.root / 'bin/python').write_text('This is not an interpreter')
        before = self.snapshot()
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('process')), patch.object(socket.socket, 'connect', side_effect=AssertionError('network')):
            result = self.inspect()
        self.assertEqual(result['status'], 'metadata_and_evaluator_source_match')
        self.assertEqual(result['versions'], {'agent-skill-eval': '0.7.0'})
        self.assertIsNone(result['packages'][0]['artifact_integrity'])
        self.assertEqual(before, self.snapshot())

    def test_source_drift_and_missing_source_block(self):
        self.source.write_text('changed')
        self.assertIn('Missing or changed evaluator source', self.inspect()['blockers'])
        self.source.unlink()
        self.assertIn('Missing or changed evaluator source', self.inspect()['blockers'])

    def test_missing_and_wrong_package_versions_are_reported(self):
        self.metadata.write_text('Name: agent-skill-eval\nVersion: 0.8.0\n')
        self.assertEqual(self.inspect()['packages'][0]['observed_version'], '0.8.0')
        self.assertTrue(self.inspect()['blockers'])
        self.metadata.unlink()
        self.metadata.parent.rmdir()
        self.assertIsNone(self.inspect()['packages'][0]['observed_version'])
        self.assertTrue(self.inspect()['blockers'])

    def test_duplicate_distribution_and_headers_are_rejected(self):
        extra = self.distribution('duplicate', 'Agent_Skill.Eval', '0.7.0')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.inspect()
        extra.unlink()
        extra.parent.rmdir()
        self.metadata.write_text('Name: agent-skill-eval\nName: other\nVersion: 0.7.0\n')
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            self.inspect()

    def test_invalid_identity_never_enters_result(self):
        for name in ('bad name', 'bad/secret', 'bad\x1bname', 'ä'):
            with self.subTest(name=name):
                self.metadata.write_text(f'Name: {name}\nVersion: 0.7.0\n')
                with self.assertRaises(ValueError):
                    self.inspect()

    def test_unselected_distribution_blocks_but_bootstrap_is_separate(self):
        self.distribution('pip-24.3.1', 'pip', '24.3.1')
        self.assertEqual(self.inspect()['bootstrap_pip_version'], '24.3.1')
        self.assertFalse(self.inspect()['blockers'])
        self.distribution('extra-1.0', 'extra', '1.0')
        self.assertEqual(self.inspect()['unexpected_distributions'], ['extra'])
        self.assertTrue(self.inspect()['blockers'])

    def test_startup_hooks_are_detected_without_reading_them(self):
        for name in ('run.pth', 'sitecustomize.py', 'usercustomize.pyc'):
            with self.subTest(name=name):
                hook = self.site / name
                os.mkfifo(hook)
                self.assertTrue(self.inspect()['startup_hooks_present'])
                self.assertTrue(self.inspect()['blockers'])
                hook.unlink()

    def test_metadata_links_pipes_and_oversized_inputs_are_rejected(self):
        self.metadata.unlink()
        os.mkfifo(self.metadata)
        with self.assertRaises(ValueError):
            self.inspect()
        self.metadata.unlink()
        self.metadata.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.inspect()
        self.metadata.unlink()
        os.link(self.source, self.metadata)
        with self.assertRaises(ValueError):
            self.inspect()
        self.metadata.unlink()
        self.metadata.write_bytes(b'x' * (1024**2 + 1))
        with self.assertRaises(ValueError):
            self.inspect()

    def test_linked_package_directory_and_source_escape_are_rejected(self):
        original = self.metadata.parent
        renamed = self.site / 'stored'
        original.rename(renamed)
        original.symlink_to(renamed, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.inspect()
        original.unlink()
        renamed.rename(original)
        self.stack['evaluator']['source_files'] = {'../outside': 'b'*64}
        with self.assertRaises(ValueError):
            self.inspect()

    def test_protected_runtime_and_nonisolated_configuration_are_rejected(self):
        with patch.dict(os.environ, {'CODEX_HOME': str(self.root)}), self.assertRaises(ValueError):
            self.inspect()
        for text in ('version = 3.12.1\ninclude-system-site-packages = false',
                     'version = 3.13.1\ninclude-system-site-packages = true'):
            (self.root / 'pyvenv.cfg').write_text(text)
            with self.assertRaises(ValueError):
                self.inspect()

    def test_shared_reader_keeps_json_behavior_and_rejects_hardlinks(self):
        path = self.root / 'data.json'
        path.write_text('{"valid":true}')
        self.assertEqual(read_json(path), {'valid': True})
        os.link(path, self.root / 'alias.json')
        with self.assertRaises(ValueError):
            read_bytes(path)


if __name__ == '__main__':
    unittest.main()
