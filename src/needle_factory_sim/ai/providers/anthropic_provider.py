"""Anthropic (Claude) adapter: structured outputs via messages.parse(),
with a JSON fallback for models or SDKs that do not support it.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from ...models import ExecutionPlan
from .base import CloudPlannerError, PlanAttempt, json_fallback_instruction

MODEL_HINT = "e.g. claude-opus-5"
KEY_HINT = "sk-ant-…  (session only, never stored)"

# Plans are small; this only needs to cover one ExecutionPlan JSON object.
MAX_TOKENS = 4096


def _client(api_key: str, timeout_s: float):
    import anthropic

    # timeout is in seconds for the Anthropic SDK; no retries so an abandoned
    # request costs at most one timeout.
    return anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=0)


def request_plan(
    api_key: str, model_id: str, system_prompt: str, user_message: str, timeout_s: float
) -> PlanAttempt:
    import anthropic

    client = _client(api_key, timeout_s)
    try:
        response = client.messages.parse(
            model=model_id,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            output_format=ExecutionPlan,
        )
        if getattr(response, "stop_reason", None) == "refusal":
            raise CloudPlannerError(
                "INVALID_STRUCTURED_RESPONSE", "Model refused the planning request"
            )
        plan = getattr(response, "parsed_output", None)
        if plan is None:
            raise CloudPlannerError(
                "INVALID_STRUCTURED_RESPONSE", "Model returned no parsed plan"
            )
        return PlanAttempt(plan=plan)
    except CloudPlannerError:
        raise
    except Exception as exc:
        # Only fall back when structured outputs are unavailable for this
        # model/SDK pair — never to paper over an auth or network failure.
        if not isinstance(exc, (anthropic.BadRequestError, AttributeError, TypeError)):
            raise

    schema = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False)
    response = client.messages.create(
        model=model_id,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message + json_fallback_instruction(schema)}],
    )
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    try:
        plan = ExecutionPlan.model_validate_json(_strip_code_fence(text))
    except ValidationError as verr:
        raise CloudPlannerError(
            "PLAN_VALIDATION_FAILED", f"Cloud response failed validation: {verr}"
        ) from verr
    return PlanAttempt(plan=plan, used_json_fallback=True)


def _strip_code_fence(text: str) -> str:
    """Without a response format the model may wrap the JSON in a code fence."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    return body.rsplit("```", 1)[0].strip()


def test_connection(api_key: str, model_id: str, timeout_s: float) -> None:
    _client(api_key, timeout_s).models.retrieve(model_id)


def classify_error(exc: Exception) -> str:
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return "AUTHENTICATION_ERROR"
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "PERMISSION_ERROR"
    if isinstance(exc, anthropic.RateLimitError):
        return "RATE_LIMIT"
    if isinstance(exc, anthropic.APITimeoutError):
        return "TIMEOUT"
    if isinstance(exc, anthropic.APIConnectionError):
        return "NETWORK_ERROR"
    if isinstance(exc, anthropic.NotFoundError):
        return "UNSUPPORTED_MODEL"
    if isinstance(exc, anthropic.BadRequestError):
        return "BAD_REQUEST"
    if isinstance(exc, anthropic.APIStatusError):
        return "ANTHROPIC_ERROR"
    if isinstance(exc, anthropic.APIError):
        return "ANTHROPIC_ERROR"
    return "UNKNOWN_ERROR"
