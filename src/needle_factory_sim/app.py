"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.show()

    # Dev/smoke helper: --screenshot <path> [--exit-after-ms N] grabs the live
    # window (real engine state included) and optionally quits. Not a demo fake.
    args = sys.argv[1:]
    if "--screenshot" in args:
        path = args[args.index("--screenshot") + 1]
        delay_ms = 8000
        if "--exit-after-ms" in args:
            delay_ms = int(args[args.index("--exit-after-ms") + 1])

        def _grab() -> None:
            window.grab().save(path)
            app.quit()

        QTimer.singleShot(delay_ms, _grab)

    return app.exec()
