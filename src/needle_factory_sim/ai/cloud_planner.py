"""Cloud planner: builds the full factory snapshot context and asks an OpenAI
model for a structured ExecutionPlan. The Cloud LLM never executes tools; its
plan is strictly validated and then executed step-by-step by PlanExecutor
through the deterministic FactoryController.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ..constants import (
    ADJACENCY,
    CARGO_DAMAGE_HP_PER_SECOND,
    CLOUD_ACTION_WHITELIST,
    CLOUD_REQUEST_TIMEOUT_S,
    PLAN_MAX_SINGLE_WAIT_S,
    PLAN_MAX_STEPS,
    PLAN_MAX_TOTAL_WAIT_S,
    SAFE_TEMP_MAX_C,
    SAFE_TEMP_MIN_C,
    TEMP_SETPOINT_MAX_C,
    TEMP_SETPOINT_MIN_C,
    TEMPERATURE_RATE_C_PER_SECOND,
)
from ..models import ExecutionPlan, FactoryState, SectorKind

CLOUD_SYSTEM_PROMPT = """You are a deterministic planning component for a factory simulation.

You do not execute tools.
Return exactly one ExecutionPlan that conforms to the provided schema.

Use only the actions explicitly listed in the context.
Do not invent sectors, paths, doors, temperatures, rules, or hidden state.

All plan actions execute sequentially in their listed order.

set_temperature changes a sector's target temperature immediately,
but its current temperature changes gradually over time.

Temperature transitions in different sectors run concurrently.

Use wait when physical time must pass before a later action becomes safe.

Never move the robot into a sector whose actual temperature at execution
time would be outside the cargo safe range.

Sector B requires its entry door to be open before entering.

Prefer a safe non-contaminated route when one exists.

If sector C is used, its contamination must be reset after leaving it
before the mission can be considered fully successful.

Do not use or request emergency_stop.

Prefer a safe plan over a shorter plan.

If no safe plan can be produced from the current state,
return status=cannot_plan and an empty steps array.

Do not ask the user a follow-up question.

If the user's request is Korean, write summary and reason fields in Korean.
"""


def build_planner_context(
    state: FactoryState, user_request: str, request_id: str
) -> dict[str, Any]:
    """Snapshot of the live factory state plus explicit rules for the Cloud planner."""
    sectors = {}
    for sid, sector in state.sectors.items():
        info: dict[str, Any] = {
            "kind": sector.kind.value,
            "current_temperature_c": round(sector.current_temperature, 1),
            "target_temperature_c": round(sector.target_temperature, 1),
            "temperature_status": sector.temperature_state.value,
        }
        if sector.kind is SectorKind.DOOR:
            info["door_open"] = bool(sector.door_open)
        if sector.kind is SectorKind.CONTAMINATED:
            info["used"] = sector.used
            info["needs_reset"] = sector.needs_reset
        sectors[sid] = info

    return {
        "request_id": request_id,
        "user_request": user_request,
        "goal": "Transport the cargo safely to the goal sector without destroying it.",
        "robot": {"current_sector": state.robot_sector},
        "cargo": {
            "hp": round(state.cargo_hp, 1),
            "safe_temperature_min_c": SAFE_TEMP_MIN_C,
            "safe_temperature_max_c": SAFE_TEMP_MAX_C,
            "damage_hp_per_second_outside_safe_range": CARGO_DAMAGE_HP_PER_SECOND,
        },
        "simulation": {"status": state.status.value},
        "map": {"adjacency": {k: sorted(v) for k, v in ADJACENCY.items()}},
        "sectors": sectors,
        "rules": {
            "movement": {
                "adjacent_only": True,
                "one_sector_per_move": True,
                "target_temperature_must_be_safe": True,
                "sector_b_requires_open_door": True,
            },
            "temperature": {
                "safe_min_c": SAFE_TEMP_MIN_C,
                "safe_max_c": SAFE_TEMP_MAX_C,
                "transition_rate_c_per_second": TEMPERATURE_RATE_C_PER_SECOND,
                "setpoint_range_c": [TEMP_SETPOINT_MIN_C, TEMP_SETPOINT_MAX_C],
            },
            "contamination": {
                "sector": "C",
                "enter_sets_used": True,
                "leave_sets_needs_reset": True,
                "reset_required_for_full_success": True,
                "reset_only_when_robot_outside_sector": True,
            },
            "mission": {
                "goal_sector": "E",
                "cargo_hp_must_be_above_zero": True,
                "no_pending_reset_for_full_success": True,
            },
            "execution": {
                "actions_execute_sequentially": True,
                "temperature_transitions_run_concurrently": True,
                "max_plan_steps": PLAN_MAX_STEPS,
                "max_single_wait_seconds": PLAN_MAX_SINGLE_WAIT_S,
                "max_total_wait_seconds": PLAN_MAX_TOTAL_WAIT_S,
            },
        },
        "available_actions": sorted(CLOUD_ACTION_WHITELIST),
    }


class CloudPlannerError(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass
class CloudPlanResult:
    request_id: str
    plan: ExecutionPlan | None
    error_category: str | None
    error_message: str | None
    latency_s: float
    model_id: str


def _classify_openai_error(exc: Exception) -> str:
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


def _sanitize(message: str, api_key: str) -> str:
    # An error text must never leak the session API key.
    return message.replace(api_key, "***") if api_key else message


def request_plan(
    api_key: str, model_id: str, context: dict[str, Any], request_id: str
) -> CloudPlanResult:
    """Blocking OpenAI call — must run on the Cloud worker thread, never the UI thread."""
    from openai import OpenAI

    started = time.monotonic()

    def _elapsed() -> float:
        return time.monotonic() - started

    # The key comes from the in-memory session only and is passed explicitly;
    # environment variables are intentionally not consulted.
    client = OpenAI(api_key=api_key, timeout=CLOUD_REQUEST_TIMEOUT_S, max_retries=1)
    user_message = (
        "Factory context (JSON):\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\n\nUser request:\n"
        + str(context.get("user_request", ""))
    )
    messages = [
        {"role": "system", "content": CLOUD_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    plan: ExecutionPlan | None = None
    try:
        try:
            # Preferred: SDK structured outputs parsing straight into the schema.
            completion = client.chat.completions.parse(
                model=model_id, messages=messages, response_format=ExecutionPlan
            )
            message = completion.choices[0].message
            if getattr(message, "refusal", None):
                raise CloudPlannerError("INVALID_STRUCTURED_RESPONSE", str(message.refusal))
            plan = message.parsed
            if plan is None:
                raise CloudPlannerError(
                    "INVALID_STRUCTURED_RESPONSE", "Model returned no parsed plan"
                )
        except CloudPlannerError:
            raise
        except Exception as exc:
            import openai

            # Fall back to plain JSON mode only when structured outputs are
            # unsupported by the model/SDK combination, then validate strictly.
            if not isinstance(exc, (openai.BadRequestError, AttributeError, TypeError)):
                raise
            schema_hint = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False)
            fallback_messages = [
                messages[0],
                {
                    "role": "user",
                    "content": user_message
                    + "\n\nReturn ONLY a JSON object conforming to this JSON Schema:\n"
                    + schema_hint,
                },
            ]
            completion = client.chat.completions.create(
                model=model_id,
                messages=fallback_messages,
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content or ""
            try:
                plan = ExecutionPlan.model_validate_json(content)
            except ValidationError as verr:
                raise CloudPlannerError(
                    "PLAN_VALIDATION_FAILED", f"Cloud response failed validation: {verr}"
                ) from verr
    except CloudPlannerError as cpe:
        return CloudPlanResult(
            request_id=request_id,
            plan=None,
            error_category=cpe.category,
            error_message=_sanitize(str(cpe), api_key),
            latency_s=_elapsed(),
            model_id=model_id,
        )
    except ValidationError as verr:
        return CloudPlanResult(
            request_id=request_id,
            plan=None,
            error_category="PLAN_VALIDATION_FAILED",
            error_message=_sanitize(str(verr), api_key),
            latency_s=_elapsed(),
            model_id=model_id,
        )
    except Exception as exc:
        return CloudPlanResult(
            request_id=request_id,
            plan=None,
            error_category=_classify_openai_error(exc),
            error_message=_sanitize(f"{type(exc).__name__}: {exc}", api_key),
            latency_s=_elapsed(),
            model_id=model_id,
        )

    return CloudPlanResult(
        request_id=request_id,
        plan=plan,
        error_category=None,
        error_message=None,
        latency_s=_elapsed(),
        model_id=model_id,
    )
