"""Capacity reservation constructors; persistence lives in the shared receipt store."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .models import CapacityReservation


def reservation(
    *,
    resource_id: str,
    execution_id: str,
    maximum_quantity: Decimal,
    unit: str,
    expires_at: datetime,
    idempotency_key: str,
) -> CapacityReservation:
    return CapacityReservation(
        resource_id=resource_id,
        execution_id=execution_id,
        maximum_quantity=maximum_quantity,
        unit=unit,
        expires_at=expires_at,
        idempotency_key=idempotency_key,
    )
