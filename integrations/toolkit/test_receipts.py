"""Exercise real command receipts and reject changed fixture provenance."""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import receipts
import stack
import test_stack

from aeep.models import ExecutionStatus, RawExecution
from aeep.store import ReceiptStore


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)

    def execute(self):
        return asyncio.run(receipts.execute([sys.executable, "-c", "print('fixture')"], self.output,
                                            {}, self.output / "receipts.sqlite3"))

    def normalized(self):
        fixture = test_stack.StackTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        import shutil
        shutil.copytree(fixture.root, self.output / "upstream")
        _, identity = self.execute()
        return receipts.normalize(
            self.output, stack.manifest(), {"fixture": "local"}, stack.collect(self.output / "upstream"),
            stack.read(stack.BASE / "fixtures/format-json/evals/evals.json"), identity, "a" * 64, "b" * 64,
            {str(p.relative_to(self.output)): stack.digest(p) for p in (self.output / "upstream").rglob("*") if p.is_file()},
        )

    def test_real_process_receipt_has_no_task_payload(self):
        text, identity = self.execute()
        self.assertEqual(text, "fixture")
        store = ReceiptStore(str(self.output / "receipts.sqlite3"))
        try:
            receipt = store.get_receipt(identity)
            self.assertEqual(receipt.status, ExecutionStatus.SUCCESS)
            self.assertEqual(receipt.metadata["scope"], "upstream coordinator batch only")
            self.assertNotIn("stdout", receipt.metadata)
            self.assertGreater(receipt.actual_resources.latency_ms, 0)
        finally:
            store.close()

    def test_failed_and_timeout_commands_retain_receipts(self):
        for status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT):
            with (self.subTest(status=status),
                  patch.object(receipts.CommandExecutor, "execute", AsyncMock(return_value=RawExecution(status=status))),
                  self.assertRaisesRegex(ValueError, "receipt retained")):
                self.execute()
        store = ReceiptStore(str(self.output / "receipts.sqlite3"))
        try:
            self.assertEqual({r.status for r in store.list_receipts()}, {ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT})
        finally:
            store.close()

    def test_canonical_bundle_resolves_and_fake_metrics_stay_missing(self):
        bundle = self.normalized()
        self.assertEqual(receipts.verify(self.output), bundle)
        self.assertEqual(len(bundle.runs), 4)
        self.assertTrue(all(r.tokens is None and r.agent_wall_seconds is None and r.cash_accounting_ref is None for r in bundle.runs))
        self.assertEqual(len({r.receipt_refs for r in bundle.runs}), 1)

    def test_verification_is_read_only_and_missing_store_is_not_created(self):
        self.normalized()
        before = {str(p.relative_to(self.output)): stack.digest(p) for p in self.output.rglob("*") if p.is_file()}
        receipts.verify(self.output)
        after = {str(p.relative_to(self.output)): stack.digest(p) for p in self.output.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        wal = self.output / "receipts.sqlite3-wal"
        wal.write_bytes(b"unfinished")
        with self.assertRaisesRegex(ValueError, "Close the fixture writer"):
            receipts.verify(self.output)
        wal.unlink()
        (self.output / "receipts.sqlite3").unlink()
        with self.assertRaisesRegex(ValueError, "store is missing"):
            receipts.verify(self.output)
        self.assertFalse((self.output / "receipts.sqlite3").exists())

    def test_linked_metadata_is_rejected_before_reading(self):
        self.normalized()
        path = self.output / "toolkit-evidence.json"
        path.unlink()
        path.symlink_to(self.output / "coordinator-receipt.json")
        with self.assertRaisesRegex(ValueError, "symlinks are excluded"):
            receipts.verify(self.output)

    def test_tampered_artifact_rejected(self):
        self.normalized()
        (self.output / "upstream/eval-format/fake/with_skill/outputs/output.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            receipts.verify(self.output)

    def test_changed_receipt_rejected(self):
        self.normalized()
        store = ReceiptStore(str(self.output / "receipts.sqlite3"))
        try:
            receipt = store.list_receipts()[0]
            receipt.metadata["scope"] = "changed"
            store.save_receipt(receipt)
        finally:
            store.close()
        with self.assertRaisesRegex(ValueError, "receipt changed"):
            receipts.verify(self.output)

    def test_changed_selection_decision_rejected(self):
        self.normalized()
        store = ReceiptStore(str(self.output / "receipts.sqlite3"))
        try:
            receipt = store.list_receipts()[0]
            decision = store.get_decision(receipt.decision_id)
            decision.selected_executor_id = "unrelated-executor"
            store.save_decision(decision)
        finally:
            store.close()
        with self.assertRaisesRegex(ValueError, "selection decision changed"):
            receipts.verify(self.output)

    def test_changed_bundle_and_live_verdict_rejected(self):
        self.normalized()
        path = self.output / "toolkit-evidence.json"
        original = path.read_text()
        data = json.loads(original)
        data["runs"][0]["verification"] = "pass"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "bundle changed"):
            receipts.verify(self.output)
        path.write_text(original)
        path = self.output / "toolkit-comparison.json"
        data = json.loads(path.read_text())
        data["outcome"] = "INCONCLUSIVE"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "unassessed"):
            receipts.verify(self.output)


if __name__ == "__main__":
    unittest.main()
