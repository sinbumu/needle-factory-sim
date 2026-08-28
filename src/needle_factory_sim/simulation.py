"""SimulationClock: QTimer-driven tick using real monotonic elapsed time."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from .constants import SIMULATION_TICK_MS
from .controller import FactoryController


class SimulationClock(QObject):
    ticked = Signal(float)  # elapsed seconds of this tick

    def __init__(self, controller: FactoryController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._last_monotonic: float | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(SIMULATION_TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        self._last_monotonic = time.monotonic()
        self._timer.start()

    def _on_tick(self) -> None:
        now = time.monotonic()
        elapsed = now - (self._last_monotonic or now)
        self._last_monotonic = now
        # Controller ignores time while emergency-stopped, which pauses
        # temperature transitions and cargo damage without stopping the timer.
        self._controller.advance_time(elapsed)
        self.ticked.emit(elapsed)
