"""Widget behaviour that is easy to break silently: command history recall and
the Cloud Settings dialog's handling of credentials.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit

from needle_factory_sim.ui.cloud_settings import CloudSettings, CloudSettingsDialog
from needle_factory_sim.ui.main_window import HistoryLineEdit


def press(widget, key) -> None:
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


@pytest.fixture
def history(qapp):
    edit = HistoryLineEdit()
    for command in ("first command", "second command"):
        edit.remember(command)
    edit.setText("")
    return edit


def test_up_walks_back_through_history(history):
    press(history, Qt.Key.Key_Up)
    assert history.text() == "second command"
    press(history, Qt.Key.Key_Up)
    assert history.text() == "first command"


def test_up_clamps_at_the_oldest_entry(history):
    for _ in range(5):
        press(history, Qt.Key.Key_Up)
    assert history.text() == "first command"


def test_down_returns_to_the_unsent_draft(history):
    history.setText("draft in progress")
    press(history, Qt.Key.Key_Up)
    assert history.text() == "second command"
    press(history, Qt.Key.Key_Down)
    assert history.text() == "draft in progress"


def test_duplicate_and_empty_commands_are_not_stored(qapp):
    edit = HistoryLineEdit()
    edit.remember("same")
    edit.remember("same")
    edit.remember("")
    assert edit._history == ["same"]


def test_history_is_empty_before_any_command(qapp):
    edit = HistoryLineEdit()
    edit.setText("typing")
    press(edit, Qt.Key.Key_Up)
    assert edit.text() == "typing"  # nothing to recall, text untouched


def test_cloud_dialog_masks_the_api_key(qapp):
    dialog = CloudSettingsDialog(CloudSettings(api_key="sk-secret", model_id="m"))
    try:
        assert dialog._key_edit.echoMode() is QLineEdit.EchoMode.Password
    finally:
        dialog.done(0)


def test_cloud_dialog_stops_its_worker_thread_on_close(qapp):
    dialog = CloudSettingsDialog(CloudSettings())
    assert dialog._thread is not None and dialog._thread.isRunning()
    dialog.done(0)
    assert dialog._thread is None


def test_closing_the_dialog_mid_test_hands_the_thread_over_instead_of_destroying_it(
    qapp, monkeypatch
):
    """Destroying a QThread blocked in a network call aborts the process."""
    import threading
    import time as _time

    from needle_factory_sim.ai import workers as workers_module
    from needle_factory_sim.ui import thread_guard

    release = threading.Event()

    def blocking_test(api_key, model_id):
        release.wait(30)  # stands in for an uncancellable network request
        return False, "released"

    monkeypatch.setattr(workers_module, "test_connection", blocking_test)

    def spin(condition, timeout: float) -> bool:
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            qapp.processEvents()
            if condition():
                return True
            _time.sleep(0.02)
        return False

    dialog = CloudSettingsDialog(CloudSettings(api_key="sk-x", model_id="m"))
    dialog._on_test()
    spin(lambda: False, 0.3)  # let the worker enter the blocking call

    dialog.done(0)
    assert dialog._thread is None
    # The still-running thread must be owned by the guard so the app's exit path
    # can hard-exit instead of letting Qt destroy it.
    assert thread_guard.has_running() is True

    release.set()
    assert spin(lambda: not thread_guard.has_running(), 10), "worker never finished"


def test_double_shutdown_is_safe(qapp):
    dialog = CloudSettingsDialog(CloudSettings())
    dialog.done(0)
    dialog.close()  # closeEvent after done() must not raise
    assert dialog._thread is None


def test_connection_test_without_credentials_reports_an_error(qapp):
    from needle_factory_sim.ai.cloud_planner import test_connection

    ok, message = test_connection("", "")
    assert ok is False
    assert "API key" in message


def test_apply_collects_the_entered_settings(qapp):
    dialog = CloudSettingsDialog(CloudSettings())
    try:
        dialog._key_edit.setText("sk-entered")
        dialog._model_edit.setText("gpt-x")
        dialog._threshold_spin.setValue(0.6)
        dialog._on_apply()
        assert dialog.result_settings is not None
        assert dialog.result_settings.api_key == "sk-entered"
        assert dialog.result_settings.model_id == "gpt-x"
        assert dialog.result_settings.threshold == pytest.approx(0.6)
        assert dialog.result_settings.configured is True
    finally:
        dialog.done(0)


def test_settings_without_a_model_id_are_not_configured():
    assert CloudSettings(api_key="sk-x").configured is False
    assert CloudSettings(model_id="m").configured is False
