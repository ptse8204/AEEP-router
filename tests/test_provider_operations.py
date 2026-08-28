from __future__ import annotations

import pytest

from aeep.errors import ConfigurationError
from aeep.provider_operations import SQLiteProviderOperationStore


def test_provider_operation_store_is_durable_and_idempotent(tmp_path) -> None:
    path = tmp_path / "provider.db"
    store = SQLiteProviderOperationStore(path)
    assert store.claim_execution_attempt("attempt-1", "sha256:a")
    assert not store.claim_execution_attempt("attempt-1", "sha256:a")
    store.store_execution_result("attempt-1", "sha256:a", {"status": "succeeded"})
    store.close()

    reopened = SQLiteProviderOperationStore(path)
    assert reopened.lookup_attempt("attempt-1") == {"status": "succeeded"}
    reopened.store_execution_result("attempt-1", "sha256:a", {"status": "succeeded"})
    with pytest.raises(ConfigurationError):
        reopened.claim_execution_attempt("attempt-1", "sha256:b")
    with pytest.raises(ConfigurationError):
        reopened.store_execution_result("attempt-1", "sha256:a", {"status": "failed"})
    reopened.close()
