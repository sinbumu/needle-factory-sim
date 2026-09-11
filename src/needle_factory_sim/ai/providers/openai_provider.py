"""OpenAI adapter: structured outputs, with a JSON-mode fallback."""

from __future__ import annotations

import json

from pydantic import ValidationError

from ...models import ExecutionPlan
from .base import CloudPlannerError, PlanAttempt, json_fallback_instruction

MODEL_HINT = "e.g. gpt-4.1"
KEY_HINT = "sk-…  (session only, never stored)"


def _client(api_key: str, timeout_s: float):
    from openai import OpenAI

    # max_retries=0 bounds an abandoned request (after Reset / E-Stop) to a
    # single timeout, since the call itself cannot be cancelled.
    return OpenAI(api_key=api_key, timeout=timeout_s, max_retries=0)


def request_plan(
    api_key: str, model_id: str, system_prompt: str, user_message: str, timeout_s: float
) -> PlanAttempt:
    import openai

    client = _client(api_key, timeout_s)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    try:
        completion = client.chat.completions.parse(
            model=model_id, messages=messages, response_format=ExecutionPlan
        )
        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            raise CloudPlannerError("INVALID_STRUCTURED_RESPONSE", str(message.refusal))
        if message.parsed is None:
            raise CloudPlannerError(
                "INVALID_STRUCTURED_RESPONSE", "Model returned no parsed plan"
            )
        return PlanAttempt(plan=message.parsed)
    except CloudPlannerError:
        raise
    except Exception as exc:
        # Fall back to plain JSON mode only when structured outputs are
        # unsupported by this model/SDK combination, then validate strictly.
        if not isinstance(exc, (openai.BadRequestError, AttributeError, TypeError)):
            raise

    schema = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False)
    completion = client.chat.completions.create(
        model=model_id,
        messages=[
            messages[0],
            {"role": "user", "content": user_message + json_fallback_instruction(schema)},
        ],
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content or ""
    try:
        plan = ExecutionPlan.model_validate_json(content)
    except ValidationError as verr:
        raise CloudPlannerError(
            "PLAN_VALIDATION_FAILED", f"Cloud response failed validation: {verr}"
        ) from verr
    return PlanAttempt(plan=plan, used_json_fallback=True)


def test_connection(api_key: str, model_id: str, timeout_s: float) -> None:
    """Resolve the model to prove the key and model id work. Raises on failure."""
    # Keep the client referenced for the duration of the call (see the note in
    # gemini_provider.test_connection).
    client = _client(api_key, timeout_s)
    client.models.retrieve(model_id)


def classify_error(exc: Exception) -> str:
    import openai

    if isinstance(exc, openai.AuthenticationError):
        return "AUTHENTICATION_ERROR"
    if isinstance(exc, openai.PermissionDeniedError):
        return "PERMISSION_ERROR"
    if isinstance(exc, openai.RateLimitError):
        return "RATE_LIMIT"
    if isinstance(exc, openai.APITimeoutError):
        return "TIMEOUT"
    if isinstance(exc, openai.APIConnectionError):
        return "NETWORK_ERROR"
    if isinstance(exc, openai.NotFoundError):
        return "UNSUPPORTED_MODEL"
    if isinstance(exc, openai.BadRequestError):
        return "BAD_REQUEST"
    if isinstance(exc, openai.OpenAIError):
        return "OPENAI_ERROR"
    return "UNKNOWN_ERROR"
