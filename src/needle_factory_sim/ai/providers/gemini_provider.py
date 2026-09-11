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
        plan = getattr(response, "parsed", None)
        if isinstance(plan, ExecutionPlan):
            return PlanAttempt(plan=plan)
        # Some models return the JSON text without a parsed object.
        if response.text:
            return PlanAttempt(plan=ExecutionPlan.model_validate_json(response.text))
        raise CloudPlannerError(
            "INVALID_STRUCTURED_RESPONSE", "Model returned no plan content"
        )
    except CloudPlannerError:
        raise
    except ValidationError as verr:
        raise CloudPlannerError(
            "PLAN_VALIDATION_FAILED", f"Cloud response failed validation: {verr}"
        ) from verr
    except Exception as exc:
        # Only a 400 means "I don't accept this schema" — retry with the schema
        # in the prompt instead. An auth, quota or network failure must surface
        # immediately rather than burn a second round trip.
        schema_rejected = (
            isinstance(exc, errors.ClientError) and getattr(exc, "code", None) == 400
        )
        if not (schema_rejected or isinstance(exc, (TypeError, ValueError))):
            raise

    schema = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False)
    response = client.models.generate_content(
        model=model_id,
        contents=user_message + json_fallback_instruction(schema),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    try:
        plan = ExecutionPlan.model_validate_json(response.text or "")
    except ValidationError as verr:
        raise CloudPlannerError(
            "PLAN_VALIDATION_FAILED", f"Cloud response failed validation: {verr}"
        ) from verr
    return PlanAttempt(plan=plan, used_json_fallback=True)


def test_connection(api_key: str, model_id: str, timeout_s: float) -> None:
    _client(api_key, timeout_s).models.get(model=model_id)


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
