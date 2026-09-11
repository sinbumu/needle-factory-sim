"""Google Gemini adapter: JSON response schema, with a prompt-schema fallback."""

from __future__ import annotations

import json

from pydantic import ValidationError

from ...models import ExecutionPlan
from .base import CloudPlannerError, PlanAttempt, json_fallback_instruction

MODEL_HINT = "e.g. gemini-2.5-pro"
KEY_HINT = "AIza…  (session only, never stored)"


def _client(api_key: str, timeout_s: float):
    from google import genai
    from google.genai import types

    # google-genai takes the request timeout in MILLISECONDS.
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
    )


def request_plan(
    api_key: str, model_id: str, system_prompt: str, user_message: str, timeout_s: float
) -> PlanAttempt:
    from google.genai import errors, types

    client = _client(api_key, timeout_s)
    response = None
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ExecutionPlan,
            ),
        )
    except ValidationError:
        # Raised while google-genai converts ExecutionPlan into its own Schema
        # type, before anything is sent: it rejects the `discriminator` key our
        # tagged union emits. Nothing reached the model, so this is "schema
        # unsupported", not a bad plan — retry with the schema in the prompt.
        # (Measured 2026-09-11 with google-genai 2.23: always rejected.)
        pass
    except errors.ClientError as exc:
        # Only a 400 means "I don't accept this schema". Auth, quota and
        # not-found failures must surface instead of burning a second request.
        if getattr(exc, "code", None) != 400:
            raise
    except (TypeError, ValueError):
        pass

    if response is not None:
        plan = getattr(response, "parsed", None)
        if isinstance(plan, ExecutionPlan):
            return PlanAttempt(plan=plan)
        # Some models return the JSON text without a parsed object.
        if response.text:
            return PlanAttempt(plan=_validate(response.text))
        raise CloudPlannerError(
            "INVALID_STRUCTURED_RESPONSE", "Model returned no plan content"
        )

    schema = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False)
    response = client.models.generate_content(
        model=model_id,
        contents=user_message + json_fallback_instruction(schema),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    return PlanAttempt(plan=_validate(response.text or ""), used_json_fallback=True)


def _validate(text: str) -> ExecutionPlan:
    """A failure here really is the model's plan being wrong, not our request."""
    try:
        return ExecutionPlan.model_validate_json(text)
    except ValidationError as verr:
        raise CloudPlannerError(
            "PLAN_VALIDATION_FAILED", f"Cloud response failed validation: {verr}"
        ) from verr


def test_connection(api_key: str, model_id: str, timeout_s: float) -> None:
    # The client must stay referenced for the whole call: genai.Client closes
    # its underlying httpx client when it is garbage-collected, so chaining off
    # a temporary fails with "Cannot send a request, as the client has been
    # closed" before the request is ever made.
    client = _client(api_key, timeout_s)
    client.models.get(model=model_id)


def classify_error(exc: Exception) -> str:
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        return {
            400: "BAD_REQUEST",
            401: "AUTHENTICATION_ERROR",
            403: "PERMISSION_ERROR",
            404: "UNSUPPORTED_MODEL",
            429: "RATE_LIMIT",
        }.get(code, "SERVER_ERROR" if isinstance(exc, errors.ServerError) else "GEMINI_ERROR")
    name = type(exc).__name__
    if "Timeout" in name:
        return "TIMEOUT"
    if "Connect" in name or "Network" in name:
        return "NETWORK_ERROR"
    return "UNKNOWN_ERROR"
