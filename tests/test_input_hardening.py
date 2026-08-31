"""Regression tests for the v0.1.5 review: malformed AI output must escalate to
CLOUD or be rejected, never be silently coerced into a valid-but-wrong action,
and never leave the UI waiting for a result that never arrives.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from needle_factory_sim.ai.needle_adapter import NeedleResult, run_single_command
from needle_factory_sim.ai.router import Route, decide_route
from needle_factory_sim.controller import FactoryController
from needle_factory_sim.models import ExecutionPlan, SimulationStatus

THRESHOLD = 0.75


def needle_call(name: str, arguments: dict, confidence: float | None = 0.99) -> NeedleResult:
    return NeedleResult(
        type="call",
        success=True,
        confidence=confidence,
        function_calls=[{"name": name, "arguments": arguments}],
    )


# ------------------------------------------------- no silent type coercion


@pytest.mark.parametrize(
    "arguments",
    [
        {"sector_id": "A", "target_c": True},  # bool would coerce to 1 °C
        {"sector_id": "A", "target_c": "30"},  # string would coerce to 30
        {"sector_id": "A", "target_c": 30.5},  # non-integer
        {"sector_id": "A", "target_c": None},
    ],
)
def test_malformed_set_temperature_arguments_escalate_to_cloud(arguments):
    decision = decide_route(needle_call("set_temperature", arguments), THRESHOLD)
    assert decision.route is Route.CLOUD, f"{arguments} was accepted as {decision.arguments}"


@pytest.mark.parametrize(
    "arguments",
    [{"sector_id": "B", "open": "yes"}, {"sector_id": "B", "open": 1}],
)
def test_malformed_toggle_door_arguments_escalate_to_cloud(arguments):
    decision = decide_route(needle_call("toggle_door", arguments), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_well_typed_arguments_still_route_local():
    decision = decide_route(
        needle_call("set_temperature", {"sector_id": "A", "target_c": 30}), THRESHOLD
    )
    assert decision.route is Route.LOCAL
    assert decision.arguments == {"sector_id": "A", "target_c": 30}


@pytest.mark.parametrize(
    "bad_arguments",
    [
        {"sector_id": "A", "target_c": True},
        {"sector_id": "A", "target_c": "30"},
    ],
)
def test_cloud_plan_rejects_coercible_arguments(bad_arguments):
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(
            {
                "status": "ready",
                "summary": "s",
                "steps": [
                    {
                        "order": 1,
                        "action": "set_temperature",
                        "arguments": bad_arguments,
                        "reason": "r",
                    }
                ],
            }
        )


def test_cloud_plan_rejects_a_boolean_wait():
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(
            {
                "status": "ready",
                "summary": "s",
                "steps": [
                    {"order": 1, "action": "wait", "arguments": {"seconds": True}, "reason": "r"}
                ],
            }
        )


# ------------------------------------------------------- confidence hygiene


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -float("inf"), 5.0, -5.0])
def test_unusable_confidence_never_routes_local(confidence):
    raw = {
        "type": "call",
        "success": True,
        "confidence": confidence,
        "function_calls": [{"name": "move_robot", "arguments": {"target_sector": "A"}}],
    }
    parsed = NeedleResult.from_raw(raw)
    assert parsed.confidence is None or math.isfinite(parsed.confidence)
    assert decide_route(parsed, THRESHOLD).route is Route.CLOUD


def test_oversized_telemetry_does_not_raise():
    huge = 10**400  # a JSON int too large for a float
    parsed = NeedleResult.from_raw(
        {
            "type": "call",
            "success": True,
            "confidence": huge,
            "prefill_tps": huge,
            "decode_tps": huge,
            "peak_ram_mb": huge,
            "function_calls": [],
        }
    )
    assert parsed.confidence is None
    assert parsed.peak_ram_mb is None
    assert decide_route(parsed, THRESHOLD).route is Route.CLOUD


def test_run_single_command_never_raises_even_if_reset_fails():
    class ExplodingAgent:
        def reset(self):
            raise RuntimeError("needle_init failed")

        def complete(self, text):  # pragma: no cover - never reached
            raise AssertionError("complete() should not be called")

    result = run_single_command(ExplodingAgent(), "do something")
    assert result.success is False
    assert "needle_init failed" in (result.error or "")
    assert decide_route(result, THRESHOLD).route is Route.CLOUD


# ------------------------------------------------------ terminal-state rules


def reach_mission_success() -> FactoryController:
    controller = FactoryController()
    controller.set_temperature("A", 30)
    controller.set_temperature("B", 30)
    controller.advance_time(10)
    controller.toggle_door("B", True)
    assert controller.move_robot("A").accepted
    assert controller.move_robot("B").accepted
    assert controller.move_robot("E").accepted
    assert controller.state.status is SimulationStatus.MISSION_SUCCESS
    return controller


def test_emergency_stop_does_not_hide_a_game_over():
    controller = FactoryController()
    controller.state.sectors["S"].current_temperature = 60
    controller.state.sectors["S"].target_temperature = 60
    controller.advance_time(20)
    assert controller.state.status is SimulationStatus.GAME_OVER

    result = controller.emergency_stop()
    assert not result.accepted
    assert result.error_code == "GAME_OVER"
    assert controller.state.status is SimulationStatus.GAME_OVER
    # The reason the run ended stays visible in later rejections too.
    assert controller.move_robot("A").error_code == "GAME_OVER"


def test_time_stops_after_game_over():
    controller = FactoryController()
    controller.state.sectors["S"].current_temperature = 60
    controller.state.sectors["S"].target_temperature = 60
    controller.advance_time(20)
    assert controller.state.status is SimulationStatus.GAME_OVER

    controller.state.sectors["A"].target_temperature = 40
    before = controller.state.sectors["A"].current_temperature
    controller.advance_time(5)
    assert controller.state.sectors["A"].current_temperature == before


def test_mission_success_is_terminal():
    controller = reach_mission_success()
    for result in (
        controller.move_robot("B"),
        controller.set_temperature("E", 60),
        controller.toggle_door("B", False),
    ):
        assert not result.accepted
        assert result.error_code == "MISSION_COMPLETE"
    assert controller.state.status is SimulationStatus.MISSION_SUCCESS


def test_a_won_mission_cannot_be_killed_by_later_time():
    controller = reach_mission_success()
    controller.state.sectors["E"].current_temperature = 60
    controller.state.sectors["E"].target_temperature = 60
    controller.advance_time(30)
    assert controller.state.cargo_hp == 100
    assert controller.state.status is SimulationStatus.MISSION_SUCCESS


def test_reset_recovers_from_a_terminal_state():
    controller = reach_mission_success()
    assert controller.reset_simulation().accepted
    assert controller.state.status is SimulationStatus.RUNNING
    assert controller.set_temperature("A", 30).accepted


def test_set_temperature_rejects_a_fractional_target():
    controller = FactoryController()
    result = controller.set_temperature("A", 30.7)
    assert not result.accepted
    assert result.error_code == "INVALID_TEMPERATURE"
    assert controller.state.sectors["A"].target_temperature == 10
