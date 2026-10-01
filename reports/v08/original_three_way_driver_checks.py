"""Zero-worker checks: unresolved three-way evidence can never become authority."""
import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from aeep.errors import ConfigurationError

PATH = Path(__file__).with_name('original_three_way_driver.py')
SPEC = importlib.util.spec_from_file_location('three_way', PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


class NoAuthority:
    def __getattr__(self, name):
        raise AssertionError('authority/worker access forbidden: ' + name)


class FailClosedChecks(unittest.TestCase):
    def test_equal_nonexistent_inventory_digests_cannot_authorize(self):
        fake = {role: 'a' * 64 for role in DRIVER.ROLES}
        with self.assertRaisesRegex(ConfigurationError, 'three-way execution unsupported'):
            DRIVER.validate(NoAuthority(), {'candidate_access_digests': fake, 'execution_authorized': True})

    def test_conflicting_access_records_cannot_authorize(self):
        fake = {'discovery_host': 'a' * 64, 'discovery_aeep_host': 'b' * 64}
        with self.assertRaisesRegex(ConfigurationError, 'three-way execution unsupported'):
            DRIVER.validate(NoAuthority(), {'candidate_access_digests': fake, 'execution_authorized': True})

    def test_unrelated_qualification_cannot_authorize(self):
        with self.assertRaisesRegex(ConfigurationError, 'three-way execution unsupported'):
            DRIVER.validate(NoAuthority(), {'qualification_report_digest': 'c' * 64, 'qualification_passed': True, 'execution_authorized': True})

    def test_run_and_validate_cli_stop_before_any_file_or_worker_access(self):
        for run in ([], ['--run']):
            with self.subTest(run=run), patch.object(sys, 'argv', [str(PATH), '--binding', '/nonexistent/fake.json', *run]), patch.object(Path, 'read_text', side_effect=AssertionError('binding file read forbidden')), self.assertRaisesRegex(ConfigurationError, 'three-way execution unsupported'):
                asyncio.run(DRIVER.main())


if __name__ == '__main__':
    unittest.main()
