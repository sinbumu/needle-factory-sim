"""AI Monitor: shows the local Needle result, routing decision, cloud plan and
execution progress. Never displays the API key (not even partially).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QBrush, QColor, QFont

from ..ai.needle_adapter import NeedleResult

NA = "N/A"

CAPTION_COLOR = "#9aa3b2"

STEP_STATUS_COLORS = {
    "PENDING": "#9aa3b2",
    "RUNNING": "#4f8cff",
    "WAITING": "#c99b2e",
    "SUCCEEDED": "#2fa066",
    "FAILED": "#c94040",
    "CANCELLED": "#b35a1f",
    "SKIPPED": "#6a7180",
}


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return NA
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


class _FieldGroup(QGroupBox):
    def __init__(self, title: str, fields: list[tuple[str, str]]) -> None:
        super().__init__(title)
        form = QFormLayout(self)
        form.setVerticalSpacing(2)
        self.labels: dict[str, QLabel] = {}
        for key, caption in fields:
            label = QLabel(NA)
            label.setWordWrap(True)
            label.setTextInteractionFlags(label.textInteractionFlags() | label.textInteractionFlags().TextSelectableByMouse)
            self.labels[key] = label
            cap = QLabel(caption)
            cap.setStyleSheet(f"color: {CAPTION_COLOR};")
            form.addRow(cap, label)

    def set(self, key: str, value: str) -> None:
        self.labels[key].setText(value if value else NA)

    def clear_all(self) -> None:
        for label in self.labels.values():
            label.setText(NA)


class AIMonitor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)

        self.route_group = _FieldGroup(
            "Routing",
            [
                ("input", "Input"),
                ("mode", "Mode"),
                ("route", "Route"),
                ("override", "Override"),
                ("reason", "Reason"),
                ("threshold", "Threshold"),
            ],
        )
        layout.addWidget(self.route_group)

        self.local_group = _FieldGroup(
            "Local — Needle 2",
            [
                ("engine", "Engine"),
                ("confidence", "Confidence"),
                ("call", "Function Call"),
                ("arguments", "Arguments"),
                ("reasoning", "Reasoning"),
                ("prefill_tps", "Prefill TPS"),
                ("decode_tps", "Decode TPS"),
                ("peak_ram", "Peak RAM"),
                ("latency", "Latency"),
                ("error", "Error"),
            ],
        )
        layout.addWidget(self.local_group)

        self.cloud_group = _FieldGroup(
            "Cloud — Planner",
            [
                ("provider", "Provider"),
                ("model", "Model ID"),
                ("configured", "Configured"),
                ("status", "Request status"),
                ("latency", "Request latency"),
                ("validation", "Plan validation"),
                ("summary", "Plan summary"),
                ("wait", "Wait countdown"),
            ],
        )
        self.cloud_group.set("provider", "OpenAI")
        self.cloud_group.set("configured", "Cloud: Not configured")
        layout.addWidget(self.cloud_group)

        self.steps_table = QTableWidget(0, 4)
        self.steps_table.setHorizontalHeaderLabels(["#", "Action", "Arguments", "Status"])
        self.steps_table.horizontalHeader().setStretchLastSection(True)
        self.steps_table.verticalHeader().setVisible(False)
        self.steps_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.steps_table.setMinimumHeight(160)
        layout.addWidget(self.steps_table)

        self.controller_group = _FieldGroup(
            "Controller (deterministic)",
            [("result", "Result"), ("message", "Message")],
        )
        layout.addWidget(self.controller_group)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(120)
        layout.addWidget(self.log)
        layout.addStretch(1)

    # ------------------------------------------------------------------ API

    def append_log(self, text: str) -> None:
        self.log.appendPlainText(text)

    def begin_command(self, text: str, mode: str, threshold: float) -> None:
        self.route_group.clear_all()
        self.local_group.set("confidence", NA)
        for key in ("confidence", "call", "arguments", "reasoning", "prefill_tps",
                    "decode_tps", "peak_ram", "latency", "error"):
            self.local_group.set(key, NA)
        for key in ("status", "latency", "validation", "summary", "wait"):
            self.cloud_group.set(key, NA)
        self.controller_group.clear_all()
        self.steps_table.setRowCount(0)
        self.route_group.set("input", text)
        self.route_group.set("mode", mode)
        self.route_group.set("threshold", f"{threshold:.2f}")

    def set_engine_state(self, state: str) -> None:
        suffix = " — Local inference available" if state == "READY" else ""
        self.local_group.set("engine", f"{state}{suffix}")

    def show_needle_result(self, result: NeedleResult) -> None:
        g = self.local_group
        g.set("confidence", _fmt(result.confidence))
        if result.function_calls:
            calls = result.function_calls
            g.set("call", "; ".join(str(c.get("name", NA)) for c in calls))
            g.set("arguments", "; ".join(str(c.get("arguments", {})) for c in calls))
        else:
            g.set("call", "[]")
            g.set("arguments", NA)
        g.set("reasoning", _fmt(result.reasoning))
        g.set("prefill_tps", _fmt(result.prefill_tps, " tok/s"))
        g.set("decode_tps", _fmt(result.decode_tps, " tok/s"))
        g.set("peak_ram", _fmt(result.peak_ram_mb, " MB"))
        g.set("latency", _fmt(result.latency_s, " s"))
        g.set("error", _fmt(result.error))

    def set_route(self, route: str, reason: str, override: bool) -> None:
        route_label = self.route_group.labels["route"]
        route_label.setText(route)
        color = "#2fa066" if route.startswith("LOCAL") else "#4f8cff"
        route_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        override_label = self.route_group.labels["override"]
        override_label.setText("TRUE" if override else "false")
        override_label.setStyleSheet(
            "color: #c99b2e; font-weight: bold;" if override else ""
        )
        self.route_group.set("reason", reason)

    def set_cloud_configured(self, configured: bool, model_id: str) -> None:
        self.cloud_group.set(
            "configured", "Cloud: Configured" if configured else "Cloud: Not configured"
        )
        self.cloud_group.set("model", model_id if configured else NA)

    def show_plan_steps(self, steps: list[tuple[str, str]]) -> None:
        """steps: list of (action, arguments-as-text)."""
        self.steps_table.setRowCount(len(steps))
        for row, (action, args) in enumerate(steps):
            self.steps_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.steps_table.setItem(row, 1, QTableWidgetItem(action))
            self.steps_table.setItem(row, 2, QTableWidgetItem(args))
            self.steps_table.setItem(row, 3, self._status_item("PENDING"))

    def _status_item(self, status: str) -> QTableWidgetItem:
        item = QTableWidgetItem(status)
        item.setForeground(QBrush(QColor(STEP_STATUS_COLORS.get(status, "#e8eaf0"))))
        font = QFont()
        font.setBold(True)
        item.setFont(font)
        return item

    def set_step_status(self, index: int, status: str) -> None:
        if 0 <= index < self.steps_table.rowCount():
            self.steps_table.setItem(index, 3, self._status_item(status))

    def show_controller_result(self, accepted: bool, message: str, error_code: str | None) -> None:
        verdict = "✅ ACCEPTED" if accepted else f"⛔ REJECTED ({error_code or 'ERROR'})"
        label = self.controller_group.labels["result"]
        label.setText(verdict)
        label.setStyleSheet(
            f"color: {'#2fa066' if accepted else '#c94040'}; font-weight: bold;"
        )
        self.controller_group.set("message", message + ("" if accepted else "\nState changed: false"))
