"""Shutdown handling for worker threads stuck in uninterruptible calls.

Needle inference and OpenAI requests are blocking calls that cannot be
cancelled. If the user quits while one is in flight, `QThread.quit()` cannot
stop it, and letting Qt destroy a running QThread aborts the process with
"QThread: Destroyed while thread is still running".

So such a thread is handed over here instead of being destroyed, and the
application's exit path checks `has_running()` to decide whether it must leave
via `os._exit()` — skipping interpreter and C++ teardown entirely, which is safe
because the process is terminating anyway.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread

_orphans: list[tuple[QThread, QObject | None]] = []


def hand_over(thread: QThread, worker: QObject | None = None) -> None:
    """Keep a still-running thread (and its worker) alive until process exit."""
    _orphans.append((thread, worker))


def stop_or_hand_over(
    thread: QThread, worker: QObject | None = None, timeout_ms: int = 3000
) -> bool:
    """Ask a worker thread to finish. Returns True if it stopped in time."""
    thread.quit()
    if thread.wait(timeout_ms):
        return True
    hand_over(thread, worker)
    return False


def has_running() -> bool:
    return any(thread.isRunning() for thread, _ in _orphans)
