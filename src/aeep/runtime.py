"""Runtime resource detection."""

from __future__ import annotations

import os

import psutil

from .models import ComputeAvailability


def detect_compute_availability() -> ComputeAvailability:
    """Best-effort host snapshot.

    The caller can override these values with agent-specific context-window or
    quota information. Host detection is intentionally conservative and never a
    substitute for cgroup-aware production capacity management.
    """

    vm = psutil.virtual_memory()
    cpu_count = os.cpu_count() or 1
    cpu_percent = psutil.cpu_percent(interval=None)
    available_fraction = max(0.05, min(1.0, 1.0 - cpu_percent / 100.0))
    # Normalize host-wide availability to a fraction; policy scoring uses this as
    # scarcity pressure, not as a hard CPU scheduler guarantee.
    _ = cpu_count
    return ComputeAvailability(
        available_memory_mb=vm.available / (1024 * 1024),
        available_cpu_fraction=available_fraction,
    )
