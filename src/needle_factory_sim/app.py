"""Application entry point."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .ui import thread_guard
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def _selfcheck(report_path: str) -> int:
    """Diagnose a packaged build: can every cloud provider adapter be loaded?

    The frozen app has no console, so the result goes to a file. This exists
    because an adapter that imports fine from source can still be missing from
    a PyInstaller bundle, which makes the buttons that touch it look dead.
    """
    from .ai.providers import all_providers, get_adapter, spec

    lines: list[str] = []
    ok = True
    lines.append(f"frozen: {getattr(sys, 'frozen', False)}")
    lines.append(f"executable: {sys.executable}")
    for provider in all_providers():
        try:
            get_adapter(provider)
            lines.append(f"{provider.value}: adapter OK")
        except Exception as exc:
            ok = False
            lines.append(f"{provider.value}: ADAPTER FAILED {type(exc).__name__}: {exc}")
            continue
        try:
            lines.append(f"{provider.value}: label={spec(provider).label}")
        except Exception as exc:
            ok = False
            lines.append(f"{provider.value}: SPEC FAILED {type(exc).__name__}: {exc}")
    # Adapters loading is necessary but not sufficient: the symptom a user sees
    # is a button that does nothing, so drive the handlers themselves.
    ok = _selfcheck_handlers(lines) and ok

    lines.append("RESULT: " + ("OK" if ok else "FAILED"))
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return 0 if ok else 1


def _selfcheck_handlers(lines: list[str]) -> bool:
    """Exercise the top-bar handlers off-screen, the way a packaged build runs them."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    ok = True
    try:
        app = QApplication.instance() or QApplication([])
        apply_theme(app)
        window = MainWindow()
        window.show()
        app.processEvents()

        checks = (
            ("reset", window._on_reset),
            ("demo A", lambda: window._on_demo("A")),
            ("tutorial open", window._show_tutorial),
            ("tutorial close", lambda: window._tutorial and window._tutorial._finish()),
            ("emergency stop", window._on_emergency_stop),
        )
        for name, handler in checks:
            try:
                handler()
                app.processEvents()
                lines.append(f"handler {name}: OK")
            except Exception as exc:
                ok = False
                lines.append(f"handler {name}: FAILED {type(exc).__name__}: {exc}")

        window.close()
        app.processEvents()
    except Exception as exc:
        ok = False
        lines.append(f"window self-check FAILED {type(exc).__name__}: {exc}")
    return ok


def main() -> int:
    argv = sys.argv[1:]
    if "--selfcheck" in argv:
        return _selfcheck(argv[argv.index("--selfcheck") + 1])

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
