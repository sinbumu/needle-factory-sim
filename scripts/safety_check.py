"""Window-level safety checks that need the real MainWindow (and therefore the
Needle engine), so they live here rather than in the CI pytest suite.

Verifies the fixes from the v0.1.4 review:
  * Emergency Stop keeps commands disabled and is not undone by `_set_busy`
  * Reset clears the monitor and re-enables commands
  * The tutorial pauses the simulation (its overlay covers Emergency Stop)
  * The tutorial cannot be opened while an inference or plan is in flight

Usage: uv run python scripts/safety_check.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from needle_factory_sim.ui.main_window import MainWindow
from needle_factory_sim.ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    QSettings("sinbumu", "NeedleFactorySim").setValue("tutorial_seen", True)
    window = MainWindow()
    window.show()

    def pump(condition, timeout=120.0, what="condition"):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            time.sleep(0.02)
        raise TimeoutError(f"timed out waiting for {what}")

    pump(lambda: "READY" in window.engine_label.text(), what="Needle READY")

    # --- Emergency Stop disables commands and survives a _set_busy(None)
    window._on_emergency_stop()
    assert window.emergency_stopped is True
    assert not window.execute_btn.isEnabled(), "Execute enabled after E-Stop"
    assert not window.input_edit.isEnabled(), "input enabled after E-Stop"
    assert window.estop_btn.isEnabled() and window.reset_btn.isEnabled(), (
        "E-Stop / Reset must always stay available"
    )
    window._set_busy(None)  # a late signal must not re-enable anything
    assert not window.execute_btn.isEnabled(), "_set_busy(None) re-enabled after E-Stop"
    print("emergency stop keeps commands disabled: OK")

    # --- Reset restores operation and clears the previous verdict
    window.monitor.show_controller_result(False, "stale verdict", "NOT_ADJACENT")
    window._on_reset()
    assert window.emergency_stopped is False
    assert window.execute_btn.isEnabled(), "Execute still disabled after Reset"
    assert window.monitor.controller_group.labels["result"].text() == "N/A", (
        "monitor still shows the previous run's verdict after Reset"
    )
    print("reset re-enables commands and clears the monitor: OK")

    # --- The tutorial pauses the world (its overlay covers Emergency Stop)
    assert window.clock.is_running, "clock should be running before the tour"
    window._show_tutorial()
    pump(lambda: window._tutorial is not None and window._tutorial.isVisible(),
         timeout=10, what="tutorial overlay")
    assert not window.clock.is_running, "simulation kept running under the tutorial"
    hp_before = window.controller.state.cargo_hp
    window.controller.state.sectors["S"].current_temperature = 60
    window.controller.state.sectors["S"].target_temperature = 60
    time.sleep(0.6)
    app.processEvents()
    assert window.controller.state.cargo_hp == hp_before, "cargo took damage during the tour"
    window._tutorial._finish()
    app.processEvents()
    assert window.clock.is_running, "clock did not resume after the tour"
    print("tutorial pauses and resumes the simulation: OK")

    # --- The tutorial button is unavailable while work is in flight
    window._set_busy("PLAN_EXECUTING")
    assert not window.tutorial_btn.isEnabled(), "tutorial reachable mid-plan"
    window._set_busy(None)
    assert window.tutorial_btn.isEnabled()
    print("tutorial blocked while busy: OK")

    window.close()
    print("SAFETY CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
