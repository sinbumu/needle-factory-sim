"""Anthropic and Gemini planner adapters.

No network access — each provider SDK's client class is replaced with a fake, so
these tests pin the request shape (schema, system prompt, timeout units) and the
guarantees that matter: structured output first, JSON fallback only when the
structured path is unsupported, strict validation, and no API key in any error.
"""

from __future__ import annotations

import json

import pytest

from needle_factory_sim.ai.cloud_planner import build_planner_context, request_plan
from needle_factory_sim.ai.providers import CloudProvider, all_providers, spec
from needle_factory_sim.constants import CLOUD_REQUEST_TIMEOUT_S
from needle_factory_sim.controller import FactoryController
from needle_factory_sim.models import ExecutionPlan

FAKE_KEY = "sk-ant-DO-NOT-LEAK-999"
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
        {
            "order": 2,
            "action": "move_robot",
            "arguments": {"target_sector": "A"},
            "reason": "advance",
        },
    ],
}


def context() -> dict:
    return build_planner_context(FactoryController().state, "plan it", "req-x")


def valid_plan() -> ExecutionPlan:
    return ExecutionPlan.model_validate(VALID_PLAN_JSON)


# --------------------------------------------------------------- registry


def test_every_provider_exposes_a_usable_spec():
    assert set(all_providers()) == {
        CloudProvider.OPENAI,
        CloudProvider.ANTHROPIC,
        CloudProvider.GEMINI,
    }
    for provider in all_providers():
        info = spec(provider)
        assert info.label and info.model_hint and info.key_hint


def test_no_model_id_is_hardcoded_as_a_default():
    """Model IDs are user-supplied; the registry may only hint at them."""
    for provider in all_providers():
        assert spec(provider).model_hint.startswith("e.g. ")


# --------------------------------------------------------------- Anthropic


class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _AnthropicResponse:
    def __init__(self, parsed_output=None, text=None, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason
        self.content = [_TextBlock(text)] if text is not None else []


class _AnthropicMessages:
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


def install_fake_anthropic(monkeypatch, *, parse=None, create=None, retrieve=None):
    import anthropic

    messages = _AnthropicMessages(parse=parse, create=create)
    captured: dict = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.messages = messages
            self.models = type(
                "Models", (), {"retrieve": staticmethod(retrieve or (lambda mid: None))}
            )()

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    return messages, captured


def test_anthropic_structured_output_plan_is_returned(monkeypatch):
    messages, captured = install_fake_anthropic(
        monkeypatch, parse=lambda **kw: _AnthropicResponse(parsed_output=valid_plan())
    )
    result = request_plan(CloudProvider.ANTHROPIC, FAKE_KEY, "claude-x", context(), "req-x")

    assert result.error_category is None
    assert result.plan is not None and len(result.plan.steps) == 2
    assert result.provider is CloudProvider.ANTHROPIC
    assert result.used_json_fallback is False
    name, kwargs = messages.calls[0]
    assert name == "parse"
    assert kwargs["output_format"] is ExecutionPlan
    assert kwargs["model"] == "claude-x"
    # The factory rules must travel as the system prompt, not buried in the turn.
    assert "deterministic planning component" in kwargs["system"]
    # Seconds for the Anthropic SDK.
    assert captured["timeout"] == CLOUD_REQUEST_TIMEOUT_S
    assert captured["api_key"] == FAKE_KEY


def test_anthropic_refusal_is_reported_not_executed(monkeypatch):
    install_fake_anthropic(
        monkeypatch,
        parse=lambda **kw: _AnthropicResponse(parsed_output=None, stop_reason="refusal"),
    )
    result = request_plan(CloudProvider.ANTHROPIC, FAKE_KEY, "m", context(), "req-x")
    assert result.plan is None
    assert result.error_category == "INVALID_STRUCTURED_RESPONSE"


def test_anthropic_falls_back_to_json_when_parse_is_unavailable(monkeypatch):
    messages, _ = install_fake_anthropic(
        monkeypatch,
        create=lambda **kw: _AnthropicResponse(text=json.dumps(VALID_PLAN_JSON)),
    )
    result = request_plan(CloudProvider.ANTHROPIC, FAKE_KEY, "m", context(), "req-x")

    assert result.error_category is None
    assert result.plan is not None
    assert result.used_json_fallback is True
    assert [name for name, _ in messages.calls] == ["create"]


def test_anthropic_fallback_tolerates_a_fenced_json_block(monkeypatch):
    fenced = "```json\n" + json.dumps(VALID_PLAN_JSON) + "\n```"
    install_fake_anthropic(monkeypatch, create=lambda **kw: _AnthropicResponse(text=fenced))
    result = request_plan(CloudProvider.ANTHROPIC, FAKE_KEY, "m", context(), "req-x")
    assert result.error_category is None
    assert result.plan is not None


def test_anthropic_invalid_plan_fails_validation(monkeypatch):
    bad = dict(VALID_PLAN_JSON)
    bad["steps"] = [
        {"order": 1, "action": "emergency_stop", "arguments": {}, "reason": "no"}
    ]
    install_fake_anthropic(
        monkeypatch, create=lambda **kw: _AnthropicResponse(text=json.dumps(bad))
    )
    result = request_plan(CloudProvider.ANTHROPIC, FAKE_KEY, "m", context(), "req-x")
    assert result.plan is None
    assert result.error_category == "PLAN_VALIDATION_FAILED"


def test_anthropic_error_never_leaks_the_api_key(monkeypatch):
    def explode(**kwargs):
        raise RuntimeError(f"upstream rejected {FAKE_KEY}")

    install_fake_anthropic(monkeypatch, parse=explode)
    result = request_plan(CloudProvider.ANTHROPIC, FAKE_KEY, "m", context(), "req-x")
    assert result.plan is None
    assert FAKE_KEY not in (result.error_message or "")
    assert "***" in (result.error_message or "")


# ------------------------------------------------------------------ Gemini


class _GeminiResponse:
    def __init__(self, parsed=None, text=None):
        self.parsed = parsed
        self.text = text


def install_fake_gemini(monkeypatch, *, generate=None, get=None):
    from google import genai

    calls: list[dict] = []
    captured: dict = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return generate(**kwargs)

        def get(self, **kwargs):
            return (get or (lambda **kw: None))(**kwargs)

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    return calls, captured


def test_gemini_structured_output_plan_is_returned(monkeypatch):
    calls, captured = install_fake_gemini(
        monkeypatch, generate=lambda **kw: _GeminiResponse(parsed=valid_plan())
    )
    result = request_plan(CloudProvider.GEMINI, FAKE_KEY, "gemini-x", context(), "req-x")

    assert result.error_category is None
    assert result.plan is not None and len(result.plan.steps) == 2
    assert result.provider is CloudProvider.GEMINI
    assert result.used_json_fallback is False
    config = calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is ExecutionPlan
    assert "deterministic planning component" in config.system_instruction
    # google-genai takes the timeout in MILLISECONDS.
    assert captured["http_options"].timeout == int(CLOUD_REQUEST_TIMEOUT_S * 1000)


def test_gemini_accepts_json_text_without_a_parsed_object(monkeypatch):
    install_fake_gemini(
        monkeypatch,
        generate=lambda **kw: _GeminiResponse(parsed=None, text=json.dumps(VALID_PLAN_JSON)),
    )
    result = request_plan(CloudProvider.GEMINI, FAKE_KEY, "m", context(), "req-x")
    assert result.error_category is None
    assert result.plan is not None


def test_gemini_retries_with_the_schema_in_the_prompt_when_rejected(monkeypatch):
    from google.genai import errors

    responses = iter(
        [
            errors.ClientError(400, {"error": {"message": "unsupported schema"}}),
            _GeminiResponse(parsed=None, text=json.dumps(VALID_PLAN_JSON)),
        ]
    )

    def generate(**kwargs):
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    calls, _ = install_fake_gemini(monkeypatch, generate=generate)
    result = request_plan(CloudProvider.GEMINI, FAKE_KEY, "m", context(), "req-x")

    assert result.error_category is None
    assert result.plan is not None
    assert result.used_json_fallback is True
    assert len(calls) == 2
    assert calls[1]["config"].response_schema is None
    assert "JSON Schema" in calls[1]["contents"]


def test_gemini_auth_failure_is_classified_and_not_retried(monkeypatch):
    from google.genai import errors

    def explode(**kwargs):
        raise errors.ClientError(401, {"error": {"message": "bad key"}})

    calls, _ = install_fake_gemini(monkeypatch, generate=explode)
    result = request_plan(CloudProvider.GEMINI, FAKE_KEY, "m", context(), "req-x")

    assert result.plan is None
    assert result.error_category == "AUTHENTICATION_ERROR"
    assert len(calls) == 1, "a bad key must not be retried as a schema problem"
    assert FAKE_KEY not in (result.error_message or "")


def test_gemini_server_error_surfaces_without_a_fallback(monkeypatch):
    from google.genai import errors

    def explode(**kwargs):
        raise errors.ServerError(503, {"error": {"message": "overloaded"}})

    calls, _ = install_fake_gemini(monkeypatch, generate=explode)
    result = request_plan(CloudProvider.GEMINI, FAKE_KEY, "m", context(), "req-x")

    assert result.plan is None
    assert len(calls) == 1, "a 5xx must not be retried as a schema problem"
    assert result.error_category in {"SERVER_ERROR", "GEMINI_ERROR"}


# ------------------------------------------------------- unavailable provider


def test_a_provider_whose_sdk_is_missing_reports_cleanly(monkeypatch):
    import needle_factory_sim.ai.cloud_planner as cp

    def boom(provider):
        raise ModuleNotFoundError("No module named 'anthropic'")

    monkeypatch.setattr(cp, "get_adapter", boom)
    result = request_plan(CloudProvider.ANTHROPIC, FAKE_KEY, "m", context(), "req-x")
    assert result.plan is None
    assert result.error_category == "PROVIDER_UNAVAILABLE"
