"""Operator-scoped temporary storage policy; never an execution grant."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .models import ContractModel, Digest, Identifier

DEFAULT_RESERVE_BYTES = 50 * 1024**3


class StorageReserveException(ContractModel):
    schema_version: Literal["aeep.toolkit.storage-exception.v1"] = "aeep.toolkit.storage-exception.v1"
    exception_id: Identifier
    purpose: Literal["toolkit-engineering"] = "toolkit-engineering"
    destination: str = Field(min_length=1, max_length=4096)
    filesystem_device: int = Field(strict=True, ge=0)
    wheel_set_sha256: Digest
    minimum_free_bytes: int = Field(strict=True, gt=0, lt=DEFAULT_RESERVE_BYTES)
    maximum_additional_bytes: int = Field(strict=True, gt=0, le=2 * 1024**3)
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def finite_window(self) -> StorageReserveException:
        if (self.issued_at.utcoffset() != timedelta(0)
                or self.expires_at.utcoffset() != timedelta(0)
                or not timedelta(0) < self.expires_at - self.issued_at <= timedelta(days=1)):
            raise ValueError("storage exception requires UTC timestamps and at most 24 hours")
        return self

    def digest(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()
