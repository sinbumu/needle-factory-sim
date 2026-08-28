"""Main window: composition root wiring UI, controller, clock, workers and executor.

State mutation happens only on the main thread through FactoryController.
Workers deliver data back via signals; stale responses are discarded by request_id.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..ai.cloud_planner import CloudPlanResult, build_planner_context
from ..ai.needle_adapter import NeedleResult
from ..ai.router import Route, decide_route
from ..ai.workers import CloudWorker, NeedleWorker
from ..constants import DEMO_PROMPTS
from ..controller import FactoryController
from ..models import ActionResult, ExecutionPlan
from ..plan_executor import PlanExecutor
from ..simulation import SimulationClock
from .ai_monitor import AIMonitor
from .cloud_settings import CloudSettings, CloudSettingsDialog
from .factory_view import FactoryView

MODE_AUTO = "AUTO"
MODE_FORCE_LOCAL = "FORCE LOCAL"
MODE_FORCE_CLOUD = "FORCE CLOUD"


class MainWindow(QMainWindow):
    _infer_requested = Signal(str, str)  # request_id, text
    _plan_requested = Signal(str, str, str, object)  # request_id, api_key, model_id, context
    _needle_reset_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Needle Factory Sim")
        self.resize(1180, 720)

        self.controller = FactoryController()
        self.cloud_settings = CloudSettings()  # API key: process memory only
        self.busy: str | None = None  # LOCAL_INFERENCE | CLOUD_PLANNING | PLAN_EXECUTING
        self.active_request_id: str | None = None
        self._current_command_text = ""

        self._build_ui()

        self.clock = SimulationClock(self.controller, self)
        self.clock.ticked.connect(self._on_tick)

        self.executor = PlanExecutor(self.controller, self)
        self.executor.step_status_changed.connect(self.monitor.set_step_status)
        self.executor.step_result.connect(self._on_step_result)
        self.executor.wait_countdown.connect(self._on_wait_countdown)
        self.executor.plan_finished.connect(self._on_plan_finished)

        self._start_workers()
        self.clock.start()
        self._refresh_view()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # Top bar
        top = QHBoxLayout()
        title = QLabel("Needle Factory Sim")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        top.addWidget(title)
        self.engine_label = QLabel("● Needle: INITIALIZING…")
        self.engine_label.setStyleSheet("color: #c99b2e; font-weight: bold;")
        top.addWidget(self.engine_label)
        top.addStretch(1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([MODE_AUTO, MODE_FORCE_LOCAL, MODE_FORCE_CLOUD])
        top.addWidget(QLabel("Routing:"))
        top.addWidget(self.mode_combo)
        self.cloud_btn = QPushButton("Cloud Settings")
        self.cloud_btn.clicked.connect(self._open_cloud_settings)
        top.addWidget(self.cloud_btn)
        self.reset_btn = QPushButton("Reset Simulation")
        self.reset_btn.clicked.connect(self._on_reset)
        top.addWidget(self.reset_btn)
        self.estop_btn = QPushButton("⛔ EMERGENCY STOP")
        self.estop_btn.setObjectName("estopButton")
        self.estop_btn.clicked.connect(self._on_emergency_stop)
        top.addWidget(self.estop_btn)
        root.addLayout(top)

        # Center: factory view | monitor
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.factory_view = FactoryView()
        self.monitor = AIMonitor()
        splitter.addWidget(self.factory_view)
        splitter.addWidget(self.monitor)
        splitter.setSizes([640, 520])
        root.addWidget(splitter, stretch=1)

        # Bottom: command input + demo presets
        bottom = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Command for the factory AI…")
        self.input_edit.returnPressed.connect(self._on_execute)
        bottom.addWidget(self.input_edit, stretch=1)
        self.demo_buttons: list[QPushButton] = []
        demo_captions = {"A": "Demo A · Local", "B": "Demo B · Safety", "C": "Demo C · Cloud"}
        for demo_key in ("A", "B", "C"):
            btn = QPushButton(demo_captions[demo_key])
            btn.setToolTip(f"Reset + prefill:\n{DEMO_PROMPTS[demo_key]}")
            btn.clicked.connect(lambda _=False, k=demo_key: self._on_demo(k))
            self.demo_buttons.append(btn)
            bottom.addWidget(btn)
        self.execute_btn = QPushButton("Execute ▶")
        self.execute_btn.setObjectName("executeButton")
        self.execute_btn.setDefault(True)
        self.execute_btn.clicked.connect(self._on_execute)
        bottom.addWidget(self.execute_btn)
        root.addLayout(bottom)

    def _start_workers(self) -> None:
        self.needle_thread = QThread(self)
        self.needle_worker = NeedleWorker()
        self.needle_worker.moveToThread(self.needle_thread)
        self.needle_thread.started.connect(self.needle_worker.initialize)
        self.needle_worker.engine_state_changed.connect(self._on_engine_state)
        self.needle_worker.engine_error.connect(
            lambda msg: self.monitor.append_log(f"[needle] engine error: {msg}")
        )
        self.needle_worker.inference_finished.connect(self._on_needle_result)
        self._infer_requested.connect(self.needle_worker.infer)
        self._needle_reset_requested.connect(self.needle_worker.reset_conversation)
        self.needle_thread.start()

        self.cloud_thread = QThread(self)
        self.cloud_worker = CloudWorker()
        self.cloud_worker.moveToThread(self.cloud_thread)
        self.cloud_worker.plan_finished.connect(self._on_cloud_result)
        self._plan_requested.connect(self.cloud_worker.plan)
        self.cloud_thread.start()

    # ------------------------------------------------------------------ helpers

    def _set_busy(self, phase: str | None) -> None:
        self.busy = phase
        enabled = phase is None
        busy_texts = {
            "LOCAL_INFERENCE": "Needle thinking…",
            "CLOUD_PLANNING": "Cloud planning…",
            "PLAN_EXECUTING": "Executing plan…",
        }
        self.execute_btn.setText(busy_texts.get(phase, "Execute ▶"))
        self.input_edit.setEnabled(enabled)
        self.execute_btn.setEnabled(enabled)
        for btn in self.demo_buttons:
            btn.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
        # Emergency Stop and Reset stay enabled at all times.

    def _refresh_view(self) -> None:
        self.factory_view.update_from(self.controller.state)

    def _mode(self) -> str:
        return self.mode_combo.currentText()

    # ------------------------------------------------------------------ slots

    def _on_tick(self, _elapsed: float) -> None:
        self._refresh_view()

    def _on_engine_state(self, state: str) -> None:
        pretty, color = {
            "INITIALIZING": ("● Needle: INITIALIZING…", "#c99b2e"),
            "READY": ("● Needle: READY (local inference available)", "#2fa066"),
            "ERROR": ("● Needle: ERROR", "#c94040"),
        }.get(state, (f"● Needle: {state}", "#9aa3b2"))
        self.engine_label.setText(pretty)
        self.engine_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.monitor.set_engine_state(state)

    def _on_demo(self, key: str) -> None:
        # Preset = reset to the identical initial state + prefill the prompt.
        self._do_reset()
        self.input_edit.setText(DEMO_PROMPTS[key])
        self.input_edit.setFocus()
        self.monitor.append_log(f"[demo] preset {key} loaded — press Execute")

    def _on_execute(self) -> None:
        if self.busy is not None:
            return
        text = self.input_edit.text().strip()
        if not text:
            return
        mode = self._mode()
        request_id = str(uuid.uuid4())
        self.active_request_id = request_id
        self._current_command_text = text
        self.monitor.begin_command(text, mode, self.cloud_settings.threshold)
        self.monitor.set_cloud_configured(
            self.cloud_settings.configured, self.cloud_settings.model_id
        )

        if mode == MODE_FORCE_CLOUD:
            self.monitor.set_route("CLOUD", "Forced by routing mode", override=True)
            self._request_cloud_plan(request_id, text)
            return

        self._set_busy("LOCAL_INFERENCE")
        self.monitor.append_log(f"[local] inference started ({request_id[:8]})")
        self._infer_requested.emit(request_id, text)

    def _on_needle_result(self, request_id: str, result: NeedleResult) -> None:
        if request_id != self.active_request_id:
            self.monitor.append_log("[local] stale response discarded")
            return
        self._set_busy(None)
        self.monitor.show_needle_result(result)
        decision = decide_route(result, self.cloud_settings.threshold)
        mode = self._mode()

        if decision.route is Route.LOCAL:
            self.monitor.set_route("LOCAL", decision.reason, override=(mode == MODE_FORCE_LOCAL))
            self._execute_local_action(decision.action, decision.arguments or {})
            return

        if mode == MODE_FORCE_LOCAL:
            self.monitor.set_route("LOCAL (no action)", decision.reason, override=True)
            self.monitor.append_log(
                f"[local] FORCE LOCAL: Needle result not executable — {decision.reason}"
            )
            self.monitor.show_controller_result(
                False, f"FORCE LOCAL: {decision.reason}. No action executed.", "LOCAL_ONLY"
            )
            return

        # AUTO escalation
        self.monitor.set_route("CLOUD", decision.reason, override=False)
        self._request_cloud_plan(request_id, self._current_command_text)

    def _request_cloud_plan(self, request_id: str, text: str) -> None:
        if not self.cloud_settings.configured:
            self.monitor.append_log(
                "[cloud] CLOUD FALLBACK REQUIRED — Cloud provider is not configured."
            )
            self.monitor.cloud_group.set("status", "CLOUD FALLBACK REQUIRED")
            self.monitor.show_controller_result(
                False,
                "Cloud provider is not configured. Factory state unchanged.",
                "CLOUD_NOT_CONFIGURED",
            )
            self._set_busy(None)
            return
        self._set_busy("CLOUD_PLANNING")
        context = build_planner_context(self.controller.state, text, request_id)
        self.monitor.cloud_group.set("status", "PLANNING…")
        self.monitor.append_log(f"[cloud] planning started ({request_id[:8]})")
        self._plan_requested.emit(
            request_id, self.cloud_settings.api_key, self.cloud_settings.model_id, context
        )

    def _on_cloud_result(self, result: CloudPlanResult) -> None:
        if result.request_id != self.active_request_id:
            self.monitor.append_log("[cloud] stale plan discarded")
            return
        self.monitor.cloud_group.set("latency", f"{result.latency_s:.2f} s")
        if result.error_category:
            self._set_busy(None)
            self.monitor.cloud_group.set("status", result.error_category)
            self.monitor.cloud_group.set(
                "validation",
                "FAILED" if result.error_category == "PLAN_VALIDATION_FAILED" else "N/A",
            )
            self.monitor.append_log(f"[cloud] {result.error_category}: {result.error_message}")
            self.monitor.show_controller_result(
                False, f"Cloud error ({result.error_category}). Factory state unchanged.", result.error_category
            )
            return

        plan = result.plan
        assert plan is not None
        self.monitor.cloud_group.set("status", "PLAN RECEIVED")
        self.monitor.cloud_group.set("validation", "PASSED")
        self.monitor.cloud_group.set("summary", plan.summary)
        if plan.status == "cannot_plan":
            self._set_busy(None)
            self.monitor.append_log(f"[cloud] cannot_plan: {plan.summary}")
            self.monitor.show_controller_result(
                False, f"Planner returned cannot_plan: {plan.summary}", "CANNOT_PLAN"
            )
            return

        self.monitor.show_plan_steps(
            [
                (step.action, json.dumps(step.arguments.model_dump(), ensure_ascii=False))
                for step in plan.steps
            ]
        )
        self._set_busy("PLAN_EXECUTING")
        self.monitor.append_log(f"[executor] plan started ({len(plan.steps)} steps)")
        self._start_plan(plan)

    def _start_plan(self, plan: ExecutionPlan) -> None:
        self.executor.start(plan)

    def _on_step_result(self, index: int, result: ActionResult) -> None:
        self.monitor.show_controller_result(result.accepted, result.message, result.error_code)
        self.monitor.append_log(
            f"[executor] step {index + 1} {result.action}: "
            f"{'OK' if result.accepted else 'REJECTED ' + str(result.error_code)}"
        )
        self._refresh_view()

    def _on_wait_countdown(self, index: int, remaining: float) -> None:
        self.monitor.cloud_group.set("wait", f"step {index + 1}: {remaining:.1f}s remaining")

    def _on_plan_finished(self, outcome: str) -> None:
        if self.busy == "PLAN_EXECUTING":
            self._set_busy(None)
        self.monitor.append_log(f"[executor] plan finished: {outcome}")
        self._refresh_view()

    # -------------------------------------------------------- local execution

    def _execute_local_action(self, action: str | None, arguments: dict) -> None:
        if action == "emergency_stop":
            self._on_emergency_stop()
            self.monitor.show_controller_result(True, "Emergency stop executed.", None)
            return
        result: ActionResult
        if action == "move_robot":
            result = self.controller.move_robot(arguments["target_sector"])
        elif action == "set_temperature":
            result = self.controller.set_temperature(arguments["sector_id"], arguments["target_c"])
        elif action == "toggle_door":
            result = self.controller.toggle_door(arguments["sector_id"], arguments["open"])
        elif action == "reset_sector":
            result = self.controller.reset_sector(arguments["sector_id"])
        else:
            result = ActionResult(
                accepted=False, action=str(action), state_changed=False,
                error_code="INVALID_ACTION", message=f"Unknown action '{action}'.",
            )
        self.monitor.show_controller_result(result.accepted, result.message, result.error_code)
        self.monitor.append_log(
            f"[controller] {result.action}: "
            f"{'ACCEPTED' if result.accepted else 'REJECTED ' + str(result.error_code)}"
        )
        self._refresh_view()

    # ------------------------------------------------------ e-stop and reset

    def _on_emergency_stop(self) -> None:
        self.active_request_id = None  # invalidate in-flight AI responses
        self.executor.cancel()
        result = self.controller.emergency_stop()
        self.monitor.append_log(f"[e-stop] {result.message}")
        self._set_busy(None)
        self._set_normal_inputs_enabled(False)
        self._refresh_view()

    def _set_normal_inputs_enabled(self, enabled: bool) -> None:
        self.input_edit.setEnabled(enabled)
        self.execute_btn.setEnabled(enabled)
        for btn in self.demo_buttons:
            btn.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)

    def _do_reset(self) -> None:
        self.active_request_id = None
        self.executor.cancel()
        self._needle_reset_requested.emit()
        self.controller.reset_simulation()
        self._set_busy(None)
        self._refresh_view()

    def _on_reset(self) -> None:
        self._do_reset()
        self.monitor.append_log("[reset] simulation reset to initial state")

    # ------------------------------------------------------------------ cloud

    def _open_cloud_settings(self) -> None:
        dialog = CloudSettingsDialog(self.cloud_settings, self)
        if dialog.exec() and dialog.result_settings is not None:
            self.cloud_settings = dialog.result_settings
            self.monitor.set_cloud_configured(
                self.cloud_settings.configured, self.cloud_settings.model_id
            )
            self.monitor.append_log(
                "[cloud] settings applied for this session "
                f"({'Configured' if self.cloud_settings.configured else 'Not configured'})"
            )

    # ------------------------------------------------------------------ close

    def closeEvent(self, event) -> None:  # noqa: N802
        for thread in (self.needle_thread, self.cloud_thread):
            thread.quit()
            thread.wait(2000)
        super().closeEvent(event)
