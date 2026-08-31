"""Confidence-based routing between the local Needle candidate and the Cloud planner."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ..constants import LOCAL_ACTION_WHITELIST
from ..models import (
    MoveRobotArgs,
    ResetSectorArgs,
    SetTemperatureArgs,
    ToggleDoorArgs,
)
from .needle_adapter import NeedleResult


class Route(str, Enum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class _EmergencyStopArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


LOCAL_ARG_MODELS: dict[str, type[BaseModel]] = {
    "move_robot": MoveRobotArgs,
    "set_temperature": SetTemperatureArgs,
    "toggle_door": ToggleDoorArgs,
    "reset_sector": ResetSectorArgs,
    "emergency_stop": _EmergencyStopArgs,
}


@dataclass
class RouteDecision:
    route: Route
    reason: str
    action: str | None = None
    arguments: dict[str, Any] | None = None


def decide_route(result: NeedleResult, threshold: float) -> RouteDecision:
    """Return LOCAL with a validated action candidate, or CLOUD with the escalation reason."""
    if result.success is False or result.error:
        return RouteDecision(Route.CLOUD, f"Needle inference error: {result.error or 'unknown'}")
    if not result.function_calls:
        return RouteDecision(Route.CLOUD, "Needle produced no function call")
    if len(result.function_calls) > 1:
        return RouteDecision(
            Route.CLOUD, f"Needle produced {len(result.function_calls)} function calls (need exactly 1)"
        )
    if result.confidence is None:
        return RouteDecision(Route.CLOUD, "Needle confidence missing or unusable")
    # Written as `not (>=)` so a NaN threshold cannot pass the gate either.
    if not (result.confidence >= threshold):
        return RouteDecision(
            Route.CLOUD, f"Confidence {result.confidence:.2f} below threshold {threshold:.2f}"
        )

    call = result.function_calls[0]
    name = call.get("name")
    arguments = call.get("arguments")
    if not isinstance(name, str) or name not in LOCAL_ACTION_WHITELIST:
        return RouteDecision(Route.CLOUD, f"Action '{name}' not in local whitelist")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return RouteDecision(Route.CLOUD, f"Arguments for '{name}' are not an object")
    try:
        validated = LOCAL_ARG_MODELS[name].model_validate(arguments)
    except ValidationError as exc:
        return RouteDecision(
            Route.CLOUD, f"Arguments for '{name}' do not match local schema: {exc.errors()[0].get('msg', 'invalid')}"
        )
    return RouteDecision(
        Route.LOCAL,
        f"Confidence {result.confidence:.2f} >= {threshold:.2f} with one valid call",
        action=name,
        arguments=validated.model_dump(),
    )
