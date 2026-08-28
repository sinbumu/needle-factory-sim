"""Cloud Settings dialog. The API key lives only in process memory for the
session; it is never written to disk, env vars, logs, or the monitor.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

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

    def _on_apply(self) -> None:
        self.result_settings = CloudSettings(
            api_key=self._key_edit.text().strip(),
            model_id=self._model_edit.text().strip(),
            threshold=float(self._threshold_spin.value()),
        )
        self.accept()

    def _on_clear_key(self) -> None:
        self._key_edit.clear()
