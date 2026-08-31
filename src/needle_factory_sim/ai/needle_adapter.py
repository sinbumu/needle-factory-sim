"""Needle 2 local adapter.

The five tools below are pure schema definitions: they never touch FactoryState.
Needle only produces tool-call *candidates*; the deterministic FactoryController
is the sole executor. `agent.run()` is intentionally never used.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

import needle

from ..constants import TEMP_SETPOINT_MAX_C, TEMP_SETPOINT_MIN_C

# ------------------------------------------------------------------ tools


@needle.tool
def move_robot(target_sector: Literal["S", "A", "B", "C", "E"]):
    """Move, go, head, drive, or send the transport robot to exactly one explicitly named adjacent sector.

    This tool does not plan a route.
    The user must explicitly identify the single target sector by name.

    Args:
        target_sector: the explicitly named destination sector to move, go, or drive to
    """
    return {"target_sector": target_sector}


@needle.tool
def set_temperature(
    sector_id: Literal["S", "A", "B", "C", "E"],
    target_c: Annotated[
        int,
        needle.Field(
            ge=TEMP_SETPOINT_MIN_C,
            le=TEMP_SETPOINT_MAX_C,
            description="target temperature in Celsius",
        ),
    ],
):
    """Set, change, adjust, warm up, or cool down the target temperature of one explicitly named factory sector.

    The user must explicitly provide both the sector and the target temperature value.
    This starts a gradual temperature transition and does not wait.

    Args:
        sector_id: the explicitly named sector whose temperature is set, changed, or adjusted
        target_c: the explicitly given target temperature in degrees Celsius
    """
    return {"sector_id": sector_id, "target_c": target_c}


@needle.tool
def toggle_door(sector_id: Literal["B"], open: bool):  # noqa: A002
    """Open or close the entry door for sector B.

    The user must explicitly request the desired door state.
    "open the door" means open=true. "close the door" or "shut the door" means open=false.

    Args:
        sector_id: the door sector (only B has a door)
        open: the desired door state. open the door = true. close or shut the door = false
    """
    return {"sector_id": sector_id, "open": open}


@needle.tool
def reset_sector(sector_id: Literal["C"]):
    """Reset, clean, clean up, decontaminate, or clear the contamination of sector C after the robot has left it.

    Use only when the user explicitly asks for the sector to be reset, cleaned, or decontaminated.

    Args:
        sector_id: the contaminated sector to reset or clean (only C is resettable)
    """
    return {"sector_id": sector_id}


@needle.tool
def emergency_stop():
    """Emergency stop: immediately stop everything, halt all operations, or abort the entire factory.

    Use when the user urgently asks to stop everything, stop now, halt, or abort.
    """
    return {}


FACTORY_TOOLS = [move_robot, set_temperature, toggle_door, reset_sector, emergency_stop]

# Fixed environment facts only — Needle must not see any Factory state.
NEEDLE_SYSTEM = "locale: ko-KR\ndevice: Windows desktop"


def build_agent() -> "needle.Needle":
    """Create the Needle agent. First call may provision/download the local engine."""
    return needle.Needle(tools=FACTORY_TOOLS, system=NEEDLE_SYSTEM)


# ------------------------------------------------------------------ response


@dataclass
class NeedleResult:
    """Normalized, crash-safe view over a Needle complete() response dict."""

    type: str | None = None
    success: bool | None = None
    error: str | None = None
    error_code: str | None = None
    function_calls: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str | None = None
    confidence: float | None = None
    prefill_tps: float | None = None
    decode_tps: float | None = None
    peak_ram_mb: float | None = None
    latency_s: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Any, latency_s: float | None = None) -> "NeedleResult":
        if not isinstance(raw, dict):
            return cls(success=False, error=f"non-dict Needle response: {type(raw).__name__}",
                       latency_s=latency_s, raw={})
        calls = raw.get("function_calls")
        if not isinstance(calls, list):
            calls = []
        calls = [c for c in calls if isinstance(c, dict)]
        # An unusable confidence must become None (which routes to CLOUD) rather
        # than slip through the threshold test: NaN fails every comparison, and
        # values outside 0..1 are not calibrated scores at all.
        confidence = _opt_float(raw.get("confidence"))
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            confidence = None
        return cls(
            type=raw.get("type"),
            success=raw.get("success"),
            error=raw.get("error"),
            error_code=raw.get("error_code"),
            function_calls=calls,
            reasoning=raw.get("reasoning"),
            confidence=confidence,
            prefill_tps=_opt_float(raw.get("prefill_tps")),
            decode_tps=_opt_float(raw.get("decode_tps")),
            peak_ram_mb=_opt_float(raw.get("peak_ram_mb")),
            latency_s=latency_s,
            raw=raw,
        )


def _opt_float(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        # A JSON integer too large for a float would otherwise raise here and
        # kill the worker slot, leaving the UI stuck on "Needle thinking…".
        return None
    return result if math.isfinite(result) else None


def run_single_command(agent: "needle.Needle", user_text: str) -> NeedleResult:
    """One user command = reset() + exactly one complete(). No agent loop.

    Never raises: the caller is a Qt worker slot, and an exception escaping it
    would leave the UI permanently disabled waiting for a result.
    """
    started = time.monotonic()
    try:
        # reset() re-binds the engine and can fail too, so it is inside the guard.
        agent.reset()
        raw = agent.complete(user_text)
        return NeedleResult.from_raw(raw, latency_s=time.monotonic() - started)
    except Exception as exc:  # inference failure must never crash the app
        return NeedleResult(
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            latency_s=time.monotonic() - started,
        )
