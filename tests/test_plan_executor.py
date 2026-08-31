"""PlanExecutor behaviour: sequencing, wait steps, failure policy and cancellation.

These run headless on a QCoreApplication; the visual step delay is shortened so
the suite stays fast while keeping the real timer code paths.
"""

from __future__ import annotations

import pytest

from needle_factory_sim import plan_executor as plan_executor_module
from needle_factory_sim.controller import FactoryController
from needle_factory_sim.models import ExecutionPlan, SimulationStatus
from needle_factory_sim.plan_executor import PlanExecutor, StepStatus


@pytest.fixture(autouse=True)
def fast_visual_delay(monkeypatch):
    monkeypatch.setattr(plan_executor_module, "EXECUTOR_VISUAL_STEP_DELAY_MS", 1)


def step(order: int, action: str, arguments: dict, reason: str = "r") -> dict:
    return {"order": order, "action": action, "arguments": arguments, "reason": reason}


def make_plan(*steps: dict, summary: str = "test plan") -> ExecutionPlan:
    return ExecutionPlan.model_validate(
        {"status": "ready", "summary": summary, "steps": list(steps)}
    )


class Recorder:
    """Captures every signal the executor emits."""

    def __init__(self, executor: PlanExecutor) -> None:
        self.statuses: list[tuple[int, str]] = []
        self.results: list[tuple[int, object]] = []
        self.countdowns: list[tuple[int, float]] = []
        self.outcomes: list[str] = []
        executor.step_status_changed.connect(lambda i, s: self.statuses.append((i, s)))
        executor.step_result.connect(lambda i, r: self.results.append((i, r)))
        executor.wait_countdown.connect(lambda i, s: self.countdowns.append((i, s)))
        executor.plan_finished.connect(self.outcomes.append)

    def status_of(self, index: int) -> list[str]:
        return [s for i, s in self.statuses if i == index]

    @property
    def done(self) -> bool:
        return bool(self.outcomes)


@pytest.fixture
def setup():
    controller = FactoryController()
    executor = PlanExecutor(controller)
    return controller, executor, Recorder(executor)


def test_full_plan_runs_to_mission_success(setup, pump):
    controller, executor, rec = setup
    # Pre-warm so no wait step is needed for this sequencing test.
    controller.set_temperature("A", 30)
    controller.set_temperature("B", 30)
    controller.advance_time(10)

    plan = make_plan(
        step(1, "toggle_door", {"sector_id": "B", "open": True}),
        step(2, "move_robot", {"target_sector": "A"}),
        step(3, "move_robot", {"target_sector": "B"}),
        step(4, "move_robot", {"target_sector": "E"}),
    )
    executor.start(plan)
    pump(lambda: rec.done, what="plan to finish")

    assert rec.outcomes == ["SUCCEEDED"]
    assert controller.state.robot_sector == "E"
    assert controller.state.status is SimulationStatus.MISSION_SUCCESS
    for i in range(4):
        assert rec.status_of(i)[-1] == StepStatus.SUCCEEDED.value
    assert executor.is_running is False


def test_failed_step_skips_remainder_and_keeps_earlier_effects(setup, pump):
    controller, executor, rec = setup
    plan = make_plan(
        step(1, "set_temperature", {"sector_id": "A", "target_c": 30}),
        step(2, "move_robot", {"target_sector": "E"}),  # not adjacent to S
        step(3, "move_robot", {"target_sector": "A"}),
    )
    executor.start(plan)
    pump(lambda: rec.done, what="plan to finish")

    assert rec.outcomes == ["FAILED"]
    assert rec.status_of(0)[-1] == StepStatus.SUCCEEDED.value
    assert rec.status_of(1)[-1] == StepStatus.FAILED.value
    assert rec.status_of(2)[-1] == StepStatus.SKIPPED.value
    # No rollback: the successful set_temperature stands.
    assert controller.state.sectors["A"].target_temperature == 30
    assert controller.state.robot_sector == "S"
    failed_result = [r for i, r in rec.results if i == 1][0]
    assert failed_result.error_code == "NOT_ADJACENT"
    assert failed_result.state_changed is False


def test_wait_step_lets_simulation_time_pass(setup, pump):
    controller, executor, rec = setup
    plan = make_plan(
        step(1, "set_temperature", {"sector_id": "A", "target_c": 30}),
        step(2, "wait", {"seconds": 1}),
        step(3, "move_robot", {"target_sector": "A"}),
    )
    executor.start(plan)
    # While the executor waits, the simulation clock keeps advancing the world.
    pump(lambda: any(s == StepStatus.WAITING.value for _, s in rec.statuses),
         what="wait step to begin")
    controller.advance_time(2.0)
    pump(lambda: rec.done, timeout=15, what="plan to finish")

    assert rec.outcomes == ["SUCCEEDED"]
    # A reached a safe temperature during the wait, so the move was accepted.
    assert controller.state.sectors["A"].current_temperature == 30
    assert controller.state.robot_sector == "A"
    assert rec.status_of(1)[-1] == StepStatus.SUCCEEDED.value
    assert any(index == 1 for index, _ in rec.countdowns)


def test_cancel_during_wait_stops_plan_and_skips_remainder(setup, pump):
    controller, executor, rec = setup
    plan = make_plan(
        step(1, "set_temperature", {"sector_id": "A", "target_c": 30}),
        step(2, "wait", {"seconds": 10}),
        step(3, "move_robot", {"target_sector": "A"}),
    )
    executor.start(plan)
    pump(lambda: any(s == StepStatus.WAITING.value for _, s in rec.statuses),
         what="wait step to begin")
    executor.cancel()

    assert rec.outcomes == ["CANCELLED"]
    assert rec.status_of(1)[-1] == StepStatus.CANCELLED.value
    assert rec.status_of(2)[-1] == StepStatus.SKIPPED.value
    assert executor.is_running is False

    # The cancelled wait must not resume the plan afterwards.
    pump.for_seconds(0.4)
    assert rec.outcomes == ["CANCELLED"]
    assert controller.state.robot_sector == "S"


def test_cancel_when_idle_is_a_noop(setup):
    _, executor, rec = setup
    executor.cancel()
    assert rec.outcomes == []


def test_starting_a_second_plan_while_running_is_rejected(setup, pump):
    _, executor, rec = setup
    plan = make_plan(step(1, "wait", {"seconds": 10}))
    executor.start(plan)
    with pytest.raises(RuntimeError):
        executor.start(plan)
    executor.cancel()
    assert rec.outcomes == ["CANCELLED"]


def test_plan_finished_is_emitted_exactly_once(setup, pump):
    _, executor, rec = setup
    plan = make_plan(
        step(1, "set_temperature", {"sector_id": "A", "target_c": 25}),
        step(2, "set_temperature", {"sector_id": "B", "target_c": 25}),
    )
    executor.start(plan)
    pump(lambda: rec.done, what="plan to finish")
    pump.for_seconds(0.3)
    assert rec.outcomes == ["SUCCEEDED"]


def test_steps_execute_against_live_state_not_the_planning_snapshot(setup, pump):
    """A plan valid when built must still be re-validated at execution time."""
    controller, executor, rec = setup
    controller.set_temperature("A", 30)
    controller.advance_time(10)  # A is safe now, so move_robot(A) would pass

    plan = make_plan(
        step(1, "set_temperature", {"sector_id": "A", "target_c": 5}),
        step(2, "move_robot", {"target_sector": "A"}),
    )
    # The world changes between planning and execution of step 2.
    executor.start(plan)
    controller.advance_time(10)  # A crashes to 5 °C before the move runs
    pump(lambda: rec.done, what="plan to finish")

    assert rec.outcomes == ["FAILED"]
    assert controller.state.robot_sector == "S"
    failed_result = [r for i, r in rec.results if i == 1][0]
    assert failed_result.error_code == "UNSAFE_TEMPERATURE"
