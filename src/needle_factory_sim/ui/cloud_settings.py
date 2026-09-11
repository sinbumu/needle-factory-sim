"""Cloud Settings dialog.

Keys live only in process memory for the session — never written to disk, env
vars, logs or the monitor. Each provider keeps its own key/model slot so that
switching the provider dropdown does not discard what you already typed.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from ..ai.providers import CloudProvider, all_providers, spec
from ..ai.workers import CloudTestWorker
from ..constants import DEFAULT_CONFIDENCE_THRESHOLD
from . import thread_guard


@dataclass
class ProviderCredentials:
    api_key: str = ""
    model_id: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model_id)


def _empty_credentials() -> dict[CloudProvider, ProviderCredentials]:
    return {provider: ProviderCredentials() for provider in all_providers()}


class CloudSettings:
    """Session-only cloud configuration, holding one slot per provider."""

    def __init__(
        self,
        provider: CloudProvider = CloudProvider.OPENAI,
        api_key: str = "",
        model_id: str = "",
        threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        credentials: dict[CloudProvider, ProviderCredentials] | None = None,
    ) -> None:
        self.provider = provider
        self.threshold = threshold
        self.credentials = credentials if credentials is not None else _empty_credentials()
        if api_key or model_id:
            self.credentials[provider] = ProviderCredentials(api_key, model_id)

    def for_provider(self, provider: CloudProvider) -> ProviderCredentials:
        return self.credentials.setdefault(provider, ProviderCredentials())

    @property
    def current(self) -> ProviderCredentials:
        return self.for_provider(self.provider)

    @property
    def api_key(self) -> str:
        return self.current.api_key

    @property
    def model_id(self) -> str:
        return self.current.model_id

    @property
    def configured(self) -> bool:
        return self.current.configured

    @property
    def provider_label(self) -> str:
        return spec(self.provider).label


class CloudSettingsDialog(QDialog):
    _test_requested = Signal(str, str, str)

    def __init__(self, current: CloudSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cloud Settings")
        self.setModal(True)
        self.result_settings: CloudSettings | None = None
        # Edit a copy, so Cancel really cancels.
        self._settings = CloudSettings(
            provider=current.provider,
            threshold=current.threshold,
            credentials={
                provider: ProviderCredentials(creds.api_key, creds.model_id)
                for provider, creds in current.credentials.items()
            },
        )

        form = QFormLayout(self)

        self._provider_combo = QComboBox()
        for provider in all_providers():
            self._provider_combo.addItem(spec(provider).label, provider.value)
        self._provider_combo.setCurrentIndex(
            self._provider_combo.findData(self._settings.provider.value)
        )
        form.addRow("Provider", self._provider_combo)

        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API Key", self._key_edit)

        self._model_edit = QLineEdit()
        form.addRow("Model ID", self._model_edit)

        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.0, 1.0)
        self._threshold_spin.setSingleStep(0.05)
        self._threshold_spin.setDecimals(2)
        self._threshold_spin.setValue(self._settings.threshold)
        form.addRow("Confidence Threshold", self._threshold_spin)

        self._test_btn = QPushButton("Test connection")
        self._test_btn.setToolTip("Verify the key and model without spending tokens")
        self._status = QLabel("")
        self._status.setWordWrap(True)
        form.addRow(self._test_btn, self._status)

        self._configured_label = QLabel("")
        self._configured_label.setWordWrap(True)
        form.addRow("Keys entered", self._configured_label)

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
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)

        self._shown_provider = self._settings.provider
        self._load_provider_fields()

        # The check is a network call, so it runs on its own thread. The thread
        # is deliberately not parented to the dialog: an in-flight request cannot
        # be interrupted, so it must be able to outlive the dialog.
        self._thread = QThread()
        self._worker = CloudTestWorker()
        self._worker.moveToThread(self._thread)
        self._worker.test_finished.connect(self._on_test_finished)
        self._test_requested.connect(self._worker.test)
        self._thread.start()

    # ------------------------------------------------------------------ fields

    def _selected_provider(self) -> CloudProvider:
        return CloudProvider(self._provider_combo.currentData())

    def _store_shown_fields(self) -> None:
        creds = self._settings.for_provider(self._shown_provider)
        creds.api_key = self._key_edit.text().strip()
        creds.model_id = self._model_edit.text().strip()

    def _load_provider_fields(self) -> None:
        provider = self._selected_provider()
        info = spec(provider)
        creds = self._settings.for_provider(provider)
        self._key_edit.setText(creds.api_key)
        self._key_edit.setPlaceholderText(info.key_hint)
        self._model_edit.setText(creds.model_id)
        self._model_edit.setPlaceholderText(info.model_hint)
        self._status.setText("")
        self._shown_provider = provider
        self._refresh_configured_label()

    def _refresh_configured_label(self) -> None:
        entered = [
            spec(provider).label
            for provider in all_providers()
            if self._settings.for_provider(provider).configured
        ]
        self._configured_label.setText(", ".join(entered) if entered else "none yet")
        self._configured_label.setStyleSheet(
            "color: #2fa066;" if entered else "color: #9aa3b2;"
        )

    def _on_provider_changed(self, _index: int) -> None:
        # Keep whatever was typed for the provider we are leaving.
        self._store_shown_fields()
        self._load_provider_fields()

    # ------------------------------------------------------------------ actions

    def _on_apply(self) -> None:
        self._store_shown_fields()
        self._settings.provider = self._selected_provider()
        self._settings.threshold = float(self._threshold_spin.value())
        self.result_settings = self._settings
        self.accept()

    def _on_clear_key(self) -> None:
        self._key_edit.clear()
        self._settings.for_provider(self._selected_provider()).api_key = ""
        self._status.setText("")
        self._refresh_configured_label()

    def _on_test(self) -> None:
        self._test_btn.setEnabled(False)
        self._status.setText("Testing…")
        self._status.setStyleSheet("color: #c99b2e;")
        self._test_requested.emit(
            self._selected_provider().value,
            self._key_edit.text().strip(),
            self._model_edit.text().strip(),
        )

    def _on_test_finished(self, ok: bool, message: str) -> None:
        self._test_btn.setEnabled(True)
        self._status.setText(("✅ " if ok else "⛔ ") + message)
        self._status.setStyleSheet(f"color: {'#2fa066' if ok else '#c94040'};")

    # ------------------------------------------------------------------ close

    def _shutdown_worker(self) -> None:
        if self._thread is None:
            return  # already shut down (done() and closeEvent can both fire)
        thread = self._thread
        worker = self._worker
        self._thread = None
        self._worker = None
        # A connection test already in flight cannot be interrupted, so hand the
        # thread over instead of letting Qt destroy it while it runs.
        thread_guard.stop_or_hand_over(thread, worker, timeout_ms=2000)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._shutdown_worker()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._shutdown_worker()
        super().done(result)
