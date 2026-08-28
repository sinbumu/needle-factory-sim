"""Qt worker objects. Needle inference and OpenAI network calls run on their own
QThreads; results come back to the main thread via signals. Workers never touch
FactoryState.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from .cloud_planner import request_plan
from .needle_adapter import build_agent, run_single_command


class NeedleWorker(QObject):
    engine_state_changed = Signal(str)  # INITIALIZING | READY | ERROR
    engine_error = Signal(str)
    inference_finished = Signal(str, object)  # request_id, NeedleResult

    def __init__(self) -> None:
        super().__init__()
        self._agent = None

    @Slot()
    def initialize(self) -> None:
        self.engine_state_changed.emit("INITIALIZING")
        try:
            self._agent = build_agent()
        except Exception as exc:
            self.engine_error.emit(f"{type(exc).__name__}: {exc}")
            self.engine_state_changed.emit("ERROR")
            return
        self.engine_state_changed.emit("READY")

    @Slot(str, str)
    def infer(self, request_id: str, user_text: str) -> None:
        if self._agent is None:
            from .needle_adapter import NeedleResult

            self.inference_finished.emit(
                request_id, NeedleResult(success=False, error="Needle engine not ready")
            )
            return
        result = run_single_command(self._agent, user_text)
        self.inference_finished.emit(request_id, result)

    @Slot()
    def reset_conversation(self) -> None:
        if self._agent is not None:
            try:
                self._agent.reset()
            except Exception:
                pass


class CloudWorker(QObject):
    plan_finished = Signal(object)  # CloudPlanResult

    @Slot(str, str, str, object)
    def plan(self, request_id: str, api_key: str, model_id: str, context: object) -> None:
        result = request_plan(api_key, model_id, context, request_id)
        self.plan_finished.emit(result)
