"""Qt worker objects. Needle inference and OpenAI network calls run on their own
QThreads; results come back to the main thread via signals. Workers never touch
FactoryState.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from .cloud_planner import request_plan, test_connection
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
        from .needle_adapter import NeedleResult

        if self._agent is None:
            self.inference_finished.emit(
                request_id, NeedleResult(success=False, error="Needle engine not ready")
            )
            return
        try:
            result = run_single_command(self._agent, user_text)
        except Exception as exc:
            # A result must always be emitted: the UI stays disabled until one
            # arrives, so an escaping exception would wedge it permanently.
            result = NeedleResult(success=False, error=f"{type(exc).__name__}: {exc}")
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
        try:
            result = request_plan(api_key, model_id, context, request_id)
        except Exception as exc:
            from .cloud_planner import CloudPlanResult

            # As with inference: always emit, or the UI waits forever.
            result = CloudPlanResult(
                request_id=request_id,
                plan=None,
                error_category="UNKNOWN_ERROR",
                error_message=type(exc).__name__,
                latency_s=0.0,
                model_id=model_id,
            )
        self.plan_finished.emit(result)


class CloudTestWorker(QObject):
    """Runs the Cloud Settings connection check off the UI thread."""

    test_finished = Signal(bool, str)

    @Slot(str, str)
    def test(self, api_key: str, model_id: str) -> None:
        ok, message = test_connection(api_key, model_id)
        self.test_finished.emit(ok, message)
