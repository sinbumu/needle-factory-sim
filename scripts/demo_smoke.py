"""End-to-end smoke test of Demo A and Demo B through the real MainWindow with
real Needle inference (no mocks, no network). Exits non-zero on failure.

Usage: uv run python scripts/demo_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

from needle_factory_sim.ui.main_window import MainWindow
from needle_factory_sim.ui.theme import apply_theme


def pump_until(app: QApplication, condition, timeout_s: float, what: str) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.02)
    raise TimeoutError(f"timed out waiting for: {what}")


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    # Keep the first-launch tutorial out of the automated run/screenshot.
    from PySide6.QtCore import QSettings

    QSettings("sinbumu", "NeedleFactorySim").setValue("tutorial_seen", True)
    window = MainWindow()
    window.show()

    pump_until(app, lambda: "READY" in window.engine_label.text(), 120, "Needle READY")
    print("engine READY")

    # ---- Demo A: local set_temperature must be accepted
    window._on_demo("A")
    window._on_execute()
    pump_until(app, lambda: window.busy is None, 60, "Demo A completion")
    state = window.controller.state
    assert state.sectors["A"].target_temperature == 30, (
        f"Demo A failed: A target is {state.sectors['A'].target_temperature}"
    )
    route = window.monitor.route_group.labels["route"].text()
    conf = window.monitor.local_group.labels["confidence"].text()
    print(f"Demo A: route={route} confidence={conf} -> A.target=30 OK")
    assert route == "LOCAL", f"Demo A routed to {route}, expected LOCAL"

    # ---- Demo B: local move_robot(E) must be REJECTED by the controller
    window._on_demo("B")
    window._on_execute()
    pump_until(app, lambda: window.busy is None, 60, "Demo B completion")
    state = window.controller.state
    assert state.robot_sector == "S", f"Demo B failed: robot moved to {state.robot_sector}"
    verdict = window.monitor.controller_group.labels["result"].text()
    print(f"Demo B: route={window.monitor.route_group.labels['route'].text()} "
          f"controller={verdict} robot still at S OK")
    assert "NOT_ADJACENT" in verdict, f"Demo B verdict was {verdict}"

    # ---- Demo C: AUTO must escalate to CLOUD (unconfigured -> fallback message)
    window._on_demo("C")
    window._on_execute()
    pump_until(app, lambda: window.busy is None, 60, "Demo C completion")
    route = window.monitor.route_group.labels["route"].text()
    cloud_status = window.monitor.cloud_group.labels["status"].text()
    print(f"Demo C: route={route} cloud_status={cloud_status}")
    assert route == "CLOUD", f"Demo C routed to {route}, expected CLOUD"
    assert cloud_status == "CLOUD FALLBACK REQUIRED", cloud_status
    assert window.controller.state.robot_sector == "S"

    window.grab().save("docs/screenshot.png")
    print("screenshot saved to docs/screenshot.png")
    window.close()
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
