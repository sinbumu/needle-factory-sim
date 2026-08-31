"""Cloud Settings dialog. The API key lives only in process memory for the
session; it is never written to disk, env vars, logs, or the monitor.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from ..ai.workers import CloudTestWorker
from ..constants import DEFAULT_CONFIDENCE_THRESHOLD


@dataclass
class CloudSettings:
    api_key: str = ""
    model_id: str = ""
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model_id)


class CloudSettingsDialog(QDialog):
    _test_requested = Signal(str, str)

    def __init__(self, current: CloudSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cloud Settings")
        self.setModal(True)
        self.result_settings: CloudSettings | None = None

        form = QFormLayout(self)
        form.addRow("Provider", QLabel("OpenAI"))

        self._key_edit = QLineEdit(current.api_key)
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("session-only, never stored")
        form.addRow("API Key", self._key_edit)

        self._model_edit = QLineEdit(current.model_id)
        self._model_edit.setPlaceholderText("e.g. gpt-4.1  (user-provided)")
        form.addRow("Model ID", self._model_edit)

        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.0, 1.0)
        self._threshold_spin.setSingleStep(0.05)
        self._threshold_spin.setDecimals(2)
        self._threshold_spin.setValue(current.threshold)
        form.addRow("Confidence Threshold", self._threshold_spin)

        self._test_btn = QPushButton("Test connection")
        self._test_btn.setToolTip("Verify the key and model without spending tokens")
        self._status = QLabel("")
        self._status.setWordWrap(True)
        form.addRow(self._test_btn, self._status)

        buttons = QDialogButtonBox()
        apply_btn = QPushButton("Apply for this session")
        clear_btn = QPushButton("Clear Key")
        cancel_btn = QPushButton("Cancel")
        buttons.addButton(apply_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(clear_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        form.addRow(buttons)

        apply_btn.clicked.connect(self._on_apply)
        clear_btn.clicked.connect(self._on_clear_key)
        cancel_btn.clicked.connect(self.reject)
        self._test_btn.clicked.connect(self._on_test)

        # The check is a network call, so it runs on its own thread.
        self._thread = QThread(self)
        self._worker = CloudTestWorker()
        self._worker.moveToThread(self._thread)
        self._worker.test_finished.connect(self._on_test_finished)
        self._test_requested.connect(self._worker.test)
        self._thread.start()

    def _on_apply(self) -> None:
        self.result_settings = CloudSettings(
            api_key=self._key_edit.text().strip(),
            model_id=self._model_edit.text().strip(),
            threshold=float(self._threshold_spin.value()),
        )
        self.accept()

    def _on_clear_key(self) -> None:
        self._key_edit.clear()
        self._status.setText("")

    def _on_test(self) -> None:
        self._test_btn.setEnabled(False)
        self._status.setText("Testing…")
        self._status.setStyleSheet("color: #c99b2e;")
        self._test_requested.emit(
            self._key_edit.text().strip(), self._model_edit.text().strip()
        )

    def _on_test_finished(self, ok: bool, message: str) -> None:
        self._test_btn.setEnabled(True)
        self._status.setText(("✅ " if ok else "⛔ ") + message)
        self._status.setStyleSheet(f"color: {'#2fa066' if ok else '#c94040'};")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._thread.quit()
        self._thread.wait(2000)
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._thread.quit()
        self._thread.wait(2000)
        super().done(result)
