"""Cloud planner: context construction, structured-output handling, error
classification and the guarantee that the session API key never leaks.

No network access — the OpenAI client is replaced with a fake.
"""

from __future__ import annotations

import json

import openai
import pytest

from needle_factory_sim.ai import cloud_planner
from needle_factory_sim.ai.cloud_planner import build_planner_context, request_plan
from needle_factory_sim.constants import (
    PLAN_MAX_SINGLE_WAIT_S,
    PLAN_MAX_STEPS,
    PLAN_MAX_TOTAL_WAIT_S,
    SAFE_TEMP_MAX_C,
    SAFE_TEMP_MIN_C,
    TEMPERATURE_RATE_C_PER_SECOND,
)
from needle_factory_sim.controller import FactoryController

FAKE_KEY = "sk-test-DO-NOT-LEAK-123456"
VALID_PLAN_JSON = {
    "status": "ready",
    "summary": "warm A then move",
    "steps": [
        {
            "order": 1,
            "action": "set_temperature",
            "arguments": {"sector_id": "A", "target_c": 30},
            "reason": "make A safe",
        },
        {"order": 2, "action": "wait", "arguments": {"seconds": 2}, "reason": "let it settle"},
        {
            "order": 3,
            "action": "move_robot",
            "arguments": {"target_sector": "A"},
            "reason": "advance",
        },
    ],
}


# --------------------------------------------------------------- context


def test_context_contains_the_required_sections():
    controller = FactoryController()
    ctx = build_planner_context(controller.state, "take the cargo to E", "req-1")
    for key in (
        "request_id", "user_request", "goal", "robot", "cargo",
        "simulation", "map", "sectors", "rules", "available_actions",
    ):
        assert key in ctx
    assert ctx["request_id"] == "req-1"
    assert ctx["user_request"] == "take the cargo to E"


def test_context_never_offers_emergency_stop_to_the_cloud():
    controller = FactoryController()
    ctx = build_planner_context(controller.state, "stop", "req-1")
    assert "emergency_stop" not in ctx["available_actions"]
    assert set(ctx["available_actions"]) == {
        "move_robot", "set_temperature", "toggle_door", "reset_sector", "wait"
    }


def test_context_reflects_live_state_including_targets_and_flags():
    controller = FactoryController()
    controller.set_temperature("A", 30)
    controller.advance_time(10)
    controller.toggle_door("B", True)
    controller.move_robot("A")

    ctx = build_planner_context(controller.state, "continue", "req-2")
    assert ctx["robot"]["current_sector"] == "A"
    # Both current and target temperature must be visible to the planner.
    assert ctx["sectors"]["A"]["current_temperature_c"] == 30
    assert ctx["sectors"]["A"]["target_temperature_c"] == 30
    assert ctx["sectors"]["B"]["door_open"] is True
    assert ctx["sectors"]["C"]["used"] is False
    assert ctx["sectors"]["C"]["needs_reset"] is False
    assert ctx["cargo"]["hp"] == 100


def test_context_rules_match_the_simulation_constants():
    controller = FactoryController()
    rules = build_planner_context(controller.state, "go", "req-3")["rules"]
    assert rules["temperature"]["safe_min_c"] == SAFE_TEMP_MIN_C
    assert rules["temperature"]["safe_max_c"] == SAFE_TEMP_MAX_C
    assert rules["temperature"]["transition_rate_c_per_second"] == TEMPERATURE_RATE_C_PER_SECOND
    assert rules["movement"]["adjacent_only"] is True
    assert rules["movement"]["sector_b_requires_open_door"] is True
    assert rules["contamination"]["reset_only_when_robot_outside_sector"] is True
    assert rules["execution"]["max_plan_steps"] == PLAN_MAX_STEPS
    assert rules["execution"]["max_single_wait_seconds"] == PLAN_MAX_SINGLE_WAIT_S
    assert rules["execution"]["max_total_wait_seconds"] == PLAN_MAX_TOTAL_WAIT_S


def test_context_is_json_serializable():
    controller = FactoryController()
    ctx = build_planner_context(controller.state, "go", "req-4")
    json.loads(json.dumps(ctx))  # would raise if the snapshot held odd objects


# ------------------------------------------------------ fake OpenAI client


class _Message:
    def __init__(self, parsed=None, refusal=None, content=None):
        self.parsed = parsed
        self.refusal = refusal
        self.content = content


class _Completion:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class _Completions:
    """Only defines `parse` when given one — its absence triggers the JSON fallback."""

    def __init__(self, parse=None, create=None):
        self.calls = []
        if parse is not None:
            self.parse = self._wrap(parse, "parse")
        if create is not None:
            self.create = self._wrap(create, "create")

    def _wrap(self, fn, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            return fn(**kwargs)

        return call


def install_fake_client(monkeypatch, *, parse=None, create=None) -> _Completions:
    completions = _Completions(parse=parse, create=create)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.init_kwargs = kwargs
            self.chat = type("Chat", (), {"completions": completions})()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    return completions


def context() -> dict:
    return build_planner_context(FactoryController().state, "plan it", "req-x")


# ----------------------------------------------------------- request_plan


def test_structured_output_plan_is_returned(monkeypatch):
    from needle_factory_sim.models import ExecutionPlan

    plan = ExecutionPlan.model_validate(VALID_PLAN_JSON)
    calls = install_fake_client(monkeypatch, parse=lambda **kw: _Completion(_Message(parsed=plan)))

    result = request_plan(FAKE_KEY, "some-model", context(), "req-x")

    assert result.error_category is None
    assert result.plan is not None
    assert len(result.plan.steps) == 3
    assert result.request_id == "req-x"
    assert result.model_id == "some-model"
    assert calls.calls[0][0] == "parse"


def test_model_refusal_is_reported_not_executed(monkeypatch):
    install_fake_client(
        monkeypatch, parse=lambda **kw: _Completion(_Message(refusal="I cannot help"))
    )
    result = request_plan(FAKE_KEY, "m", context(), "req-x")
    assert result.plan is None
    assert result.error_category == "INVALID_STRUCTURED_RESPONSE"


def test_missing_parsed_plan_is_reported(monkeypatch):
    install_fake_client(monkeypatch, parse=lambda **kw: _Completion(_Message(parsed=None)))
    result = request_plan(FAKE_KEY, "m", context(), "req-x")
    assert result.plan is None
    assert result.error_category == "INVALID_STRUCTURED_RESPONSE"


def test_falls_back_to_json_mode_when_structured_output_is_unavailable(monkeypatch):
    # No `parse` attribute at all — the old-SDK / unsupported-model path.
    calls = install_fake_client(
        monkeypatch,
        create=lambda **kw: _Completion(_Message(content=json.dumps(VALID_PLAN_JSON))),
    )
    result = request_plan(FAKE_KEY, "m", context(), "req-x")

    assert result.error_category is None
    assert result.plan is not None and len(result.plan.steps) == 3
    assert [name for name, _ in calls.calls] == ["create"]
    assert calls.calls[0][1]["response_format"] == {"type": "json_object"}


def test_invalid_json_from_fallback_fails_validation(monkeypatch):
    bad = dict(VALID_PLAN_JSON)
    bad["steps"] = [
        {
            "order": 1,
            "action": "emergency_stop",  # not a cloud action
            "arguments": {},
            "reason": "nope",
        }
    ]
    install_fake_client(
        monkeypatch, create=lambda **kw: _Completion(_Message(content=json.dumps(bad)))
    )
    result = request_plan(FAKE_KEY, "m", context(), "req-x")
    assert result.plan is None
    assert result.error_category == "PLAN_VALIDATION_FAILED"


def test_api_key_is_never_included_in_an_error_message(monkeypatch):
    def explode(**kwargs):
        raise RuntimeError(f"upstream rejected key {FAKE_KEY} for this request")

    install_fake_client(monkeypatch, parse=explode)
    result = request_plan(FAKE_KEY, "m", context(), "req-x")

    assert result.plan is None
    assert FAKE_KEY not in (result.error_message or "")
    assert "***" in (result.error_message or "")


def test_api_key_is_passed_explicitly_and_not_read_from_the_environment(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "C", (), {"parse": staticmethod(lambda **kw: _Completion(_Message(parsed=None)))}
                    )()
                },
            )()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    request_plan(FAKE_KEY, "m", context(), "req-x")

    assert captured["api_key"] == FAKE_KEY
    assert captured["timeout"] == cloud_planner.CLOUD_REQUEST_TIMEOUT_S


@pytest.mark.parametrize("latency_field", ["latency_s"])
def test_result_always_carries_request_metadata(monkeypatch, latency_field):
    install_fake_client(monkeypatch, parse=lambda **kw: _Completion(_Message(parsed=None)))
    result = request_plan(FAKE_KEY, "model-z", context(), "req-42")
    assert result.request_id == "req-42"
    assert result.model_id == "model-z"
    assert getattr(result, latency_field) >= 0
