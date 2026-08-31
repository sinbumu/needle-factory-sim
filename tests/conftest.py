"""Shared fixtures.

Tests run against the offscreen Qt platform, so no display is required in CI.
No test constructs a Needle engine or performs network I/O.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def pump(qapp):
    """Drive the Qt event loop until a condition holds (or for a fixed time)."""

    def pump_until(condition, timeout: float = 10.0, what: str = "condition"):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            qapp.processEvents()
            if condition():
                return
            time.sleep(0.005)
        raise TimeoutError(f"timed out waiting for {what}")

    def pump_for(seconds: float):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)

    pump_until.for_seconds = pump_for
    return pump_until
