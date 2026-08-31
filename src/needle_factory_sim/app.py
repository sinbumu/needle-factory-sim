"""Application entry point."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .ui import thread_guard
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

    exit_code = app.exec()

    if thread_guard.has_running():
        # A worker is still stuck in Needle inference or an OpenAI request that
        # cannot be cancelled. Normal teardown would destroy its QThread and
        # abort the process, so leave immediately instead — the OS reclaims
        # everything and nothing is left to flush.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)

    return exit_code
