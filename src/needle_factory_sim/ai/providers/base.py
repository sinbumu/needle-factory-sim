"""Shared contract for the Cloud planner's provider adapters.

Each adapter turns the same system prompt + factory context into a validated
ExecutionPlan. Adapters never execute anything and never touch FactoryState;
they only produce structured data for the deterministic controller to check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CloudProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


@dataclass(frozen=True)
class ProviderSpec:
    provider: CloudProvider
    label: str  # shown in the UI
    model_hint: str  # placeholder text, never a hardcoded default
    key_hint: str


@dataclass
class PlanAttempt:
    """What an adapter returns: a parsed plan plus how it was obtained."""

    plan: object | None  # ExecutionPlan; typed loosely to keep adapters decoupled
    used_json_fallback: bool = False


class CloudPlannerError(Exception):
    """A failure the adapter has already categorised (no HTTP status to map)."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def sanitize(message: str, api_key: str) -> str:
    """An error message must never carry the session API key."""
    return message.replace(api_key, "***") if api_key else message


def json_fallback_instruction(schema_json: str) -> str:
    return (
        "\n\nReturn ONLY a JSON object conforming to this JSON Schema:\n" + schema_json
    )
