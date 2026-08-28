"""PlanExecutor: runs a validated Cloud ExecutionPlan step by step on the main thread.

Every step is re-validated by the FactoryController against the *live* state at
execution time. A failed step skips the rest of the plan; succeeded steps are
never rolled back. Timers are cancellable for Emergency Stop / Reset.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, QTimer, Signal

from .constants import EXECUTOR_VISUAL_STEP_DELAY_MS
from .controller import FactoryController
from .models import ActionResult, ExecutionPlan, WaitStep


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class PlanExecutor(QObject):
    step_status_changed = Signal(int, str)  # step index, StepStatus value
    step_result = Signal(int, object)  # step index, ActionResult
    wait_countdown = Signal(int, float)  # step index, remaining seconds
    plan_finished = Signal(str)  # "SUCCEEDED" | "FAILED" | "CANCELLED"

    def __init__(self, controller: FactoryController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._plan: ExecutionPlan | None = None
        self._index = -1
        self._running = False

        self._advance_timer = QTimer(self)
        self._advance_timer.setSingleShot(True)
        self._advance_timer.timeout.connect(self._advance)

        self._wait_remaining = 0.0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(250)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, plan: ExecutionPlan) -> None:
        if self._running:
            raise RuntimeError("A plan is already executing")
        self._plan = plan
        self._index = -1
        self._running = True
        self._advance()

    def cancel(self) -> None:
        if not self._running:
            return
        self._advance_timer.stop()
        self._countdown_timer.stop()
        if self._plan and 0 <= self._index < len(self._plan.steps):
            self.step_status_changed.emit(self._index, StepStatus.CANCELLED.value)
            self._skip_remaining(self._index + 1)
        self._running = False
        self.plan_finished.emit("CANCELLED")

    # ------------------------------------------------------------------ internal

    def _skip_remaining(self, start: int) -> None:
        assert self._plan is not None
        for i in range(start, len(self._plan.steps)):
            self.step_status_changed.emit(i, StepStatus.SKIPPED.value)

    def _finish(self, outcome: str) -> None:
        self._running = False
        self._advance_timer.stop()
        self._countdown_timer.stop()
        self.plan_finished.emit(outcome)

    def _advance(self) -> None:
        if not self._running or self._plan is None:
            return
        self._countdown_timer.stop()
        if 0 <= self._index < len(self._plan.steps) and isinstance(
            self._plan.steps[self._index], WaitStep
        ):
            self.step_status_changed.emit(self._index, StepStatus.SUCCEEDED.value)
            self.wait_countdown.emit(self._index, 0.0)
        self._index += 1
        if self._index >= len(self._plan.steps):
            self._finish("SUCCEEDED")
            return
        step = self._plan.steps[self._index]

        if isinstance(step, WaitStep):
            self.step_status_changed.emit(self._index, StepStatus.WAITING.value)
            self._wait_remaining = float(step.arguments.seconds)
            self.wait_countdown.emit(self._index, self._wait_remaining)
            self._countdown_timer.start()
            self._advance_timer.start(step.arguments.seconds * 1000)
            return

        self.step_status_changed.emit(self._index, StepStatus.RUNNING.value)
        result = self._execute_step(step)
        self.step_result.emit(self._index, result)
        if result.accepted:
            self.step_status_changed.emit(self._index, StepStatus.SUCCEEDED.value)
            # Presentation pacing only — factory time keeps running meanwhile.
            self._advance_timer.start(EXECUTOR_VISUAL_STEP_DELAY_MS)
        else:
            self.step_status_changed.emit(self._index, StepStatus.FAILED.value)
            self._skip_remaining(self._index + 1)
            self._finish("FAILED")

    def _on_countdown_tick(self) -> None:
        # Display-only countdown; step completion is owned by _advance().
        self._wait_remaining = max(0.0, self._wait_remaining - 0.25)
        self.wait_countdown.emit(self._index, self._wait_remaining)
        if self._wait_remaining <= 0:
            self._countdown_timer.stop()

    def _execute_step(self, step) -> ActionResult:
        args = step.arguments
        if step.action == "move_robot":
            return self._controller.move_robot(args.target_sector)
        if step.action == "set_temperature":
            return self._controller.set_temperature(args.sector_id, args.target_c)
        if step.action == "toggle_door":
            return self._controller.toggle_door(args.sector_id, args.open)
        if step.action == "reset_sector":
            return self._controller.reset_sector(args.sector_id)
        return ActionResult(
            accepted=False,
            action=step.action,
            state_changed=False,
            error_code="INVALID_ACTION",
            message=f"Action '{step.action}' cannot be executed.",
        )
