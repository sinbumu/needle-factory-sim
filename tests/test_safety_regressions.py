"""Regression tests for defects found in the v0.1.4 safety review.

Each test pins one behaviour that was previously wrong.
"""

from __future__ import annotations

import pytest

from needle_factory_sim import plan_executor as plan_executor_module
from needle_factory_sim.constants import MAX_TICK_ELAPSED_S
from needle_factory_sim.controller import FactoryController
from needle_factory_sim.models import ExecutionPlan, SimulationStatus
from needle_factory_sim.plan_executor import PlanExecutor, StepStatus
from needle_factory_sim.simulation import SimulationClock


@pytest.fixture(autouse=True)
def fast_visual_delay(monkeypatch):
    monkeypatch.setattr(plan_executor_module, "EXECUTOR_VISUAL_STEP_DELAY_MS", 1)


def step(order: int, action: str, arguments: dict) -> dict:
    return {"order": order, "action": action, "arguments": arguments, "reason": "r"}


def plan_of(*steps: dict) -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {"status": "ready", "summary": "s", "steps": list(steps)}
    )


class Recorder:
    def __init__(self, executor: PlanExecutor) -> None:
        self.statuses: list[tuple[int, str]] = []
        self.outcomes: list[str] = []
        executor.step_status_changed.connect(lambda i, s: self.statuses.append((i, s)))
        executor.plan_finished.connect(self.outcomes.append)

    def status_of(self, index: int) -> list[str]:
        return [s for i, s in self.statuses if i == index]

    @property
    def done(self) -> bool:
        return bool(self.outcomes)


# --------------------------------------------------- game over aborts a plan


def test_game_over_during_a_wait_aborts_the_plan_promptly(pump):
    """Previously the plan idled for the full wait and reported it SUCCEEDED."""
    controller = FactoryController()
    executor = PlanExecutor(controller)
    rec = Recorder(executor)

    executor.start(
        plan_of(
            step(1, "wait", {"seconds": 10}),
            step(2, "move_robot", {"target_sector": "A"}),
        )
    )
    pump(lambda: any(s == StepStatus.WAITING.value for _, s in rec.statuses),
         what="wait to start")

    # Cargo is destroyed while the executor is waiting.
    controller.state.sectors["S"].current_temperature = 60
    controller.state.sectors["S"].target_temperature = 60
    controller.advance_time(20)
    assert controller.state.status is SimulationStatus.GAME_OVER

    # The plan must end on its own, well inside the 10 s wait.
    pump(lambda: rec.done, timeout=5, what="plan to abort")
    assert rec.outcomes == ["FAILED"]
    assert rec.status_of(0)[-1] == StepStatus.FAILED.value
    assert StepStatus.SUCCEEDED.value not in rec.status_of(0)
    assert rec.status_of(1)[-1] == StepStatus.SKIPPED.value
    assert executor.is_running is False


def test_emergency_stop_status_aborts_the_plan(pump):
    controller = FactoryController()
    executor = PlanExecutor(controller)
    rec = Recorder(executor)

    executor.start(
        plan_of(
            step(1, "wait", {"seconds": 10}),
            step(2, "set_temperature", {"sector_id": "A", "target_c": 30}),
        )
    )
    pump(lambda: any(s == StepStatus.WAITING.value for _, s in rec.statuses),
         what="wait to start")
    controller.emergency_stop()

    pump(lambda: rec.done, timeout=5, what="plan to abort")
    assert rec.outcomes == ["FAILED"]
    assert controller.state.sectors["A"].target_temperature == 10  # step 2 never ran


# ------------------------------------------- cancel must not relabel a step


def test_cancel_after_a_step_succeeded_keeps_it_succeeded(pump):
    """The controller already applied that step; the audit trail must say so."""
    controller = FactoryController()
    executor = PlanExecutor(controller)
    rec = Recorder(executor)

    executor.start(
        plan_of(
            step(1, "set_temperature", {"sector_id": "A", "target_c": 30}),
            step(2, "set_temperature", {"sector_id": "B", "target_c": 30}),
        )
    )
    # Cancel inside the presentation delay that follows step 1's success.
    pump(lambda: StepStatus.SUCCEEDED.value in rec.status_of(0), what="step 1 to succeed")
    executor.cancel()

    assert rec.status_of(0)[-1] == StepStatus.SUCCEEDED.value
    assert StepStatus.CANCELLED.value not in rec.status_of(0)
    assert controller.state.sectors["A"].target_temperature == 30  # really applied


def test_reaching_the_goal_finishes_the_plan_successfully(pump):
    """Trailing steps after the mission is won are unnecessary, not failures."""
    controller = FactoryController()
    controller.set_temperature("A", 30)
    controller.set_temperature("B", 30)
    controller.advance_time(10)
    controller.toggle_door("B", True)
    controller.move_robot("A")
    executor = PlanExecutor(controller)
    rec = Recorder(executor)

    executor.start(
        plan_of(
            step(1, "move_robot", {"target_sector": "B"}),
            step(2, "move_robot", {"target_sector": "E"}),  # mission succeeds here
            step(3, "set_temperature", {"sector_id": "A", "target_c": 25}),  # trailing
        )
    )
    pump(lambda: rec.done, what="plan to finish")

    assert rec.outcomes == ["SUCCEEDED"]
    assert controller.state.status is SimulationStatus.MISSION_SUCCESS
    assert rec.status_of(2)[-1] == StepStatus.SKIPPED.value


def test_cancel_during_an_in_progress_wait_still_marks_it_cancelled(pump):
    controller = FactoryController()
    executor = PlanExecutor(controller)
    rec = Recorder(executor)

    executor.start(plan_of(step(1, "wait", {"seconds": 10})))
    pump(lambda: any(s == StepStatus.WAITING.value for _, s in rec.statuses),
         what="wait to start")
    executor.cancel()
    assert rec.status_of(0)[-1] == StepStatus.CANCELLED.value


# ------------------------------------------------------------- clock guards


def test_clock_clamps_an_oversized_time_jump(qapp, monkeypatch):
    """A laptop resume must not destroy the cargo in a single tick."""
    controller = FactoryController()
    controller.state.sectors["S"].current_temperature = 60
    controller.state.sectors["S"].target_temperature = 60
    clock = SimulationClock(controller)

    fake_now = [1000.0]
    monkeypatch.setattr(
        "needle_factory_sim.simulation.time.monotonic", lambda: fake_now[0]
    )
    clock.start()
    fake_now[0] += 4 * 3600  # four hours of system suspend
    clock._on_tick()

    expected_damage = 10.0 * MAX_TICK_ELAPSED_S
    assert controller.state.cargo_hp == pytest.approx(100 - expected_damage)
    assert controller.state.status is SimulationStatus.RUNNING


def test_resume_does_not_apply_the_paused_interval(qapp, monkeypatch):
    controller = FactoryController()
    controller.state.sectors["S"].current_temperature = 60
    controller.state.sectors["S"].target_temperature = 60
    clock = SimulationClock(controller)

    fake_now = [1000.0]
    monkeypatch.setattr(
        "needle_factory_sim.simulation.time.monotonic", lambda: fake_now[0]
    )
    clock.start()
    clock.pause()
    assert clock.is_running is False

    fake_now[0] += 120.0  # two minutes reading the tutorial
    clock.resume()
    fake_now[0] += 0.1
    clock._on_tick()

    assert controller.state.cargo_hp == pytest.approx(99.0)  # 0.1 s of damage only
