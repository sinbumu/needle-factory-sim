"""Cloud planner providers.

Adapter modules are imported lazily so launching the app (and the frozen
build's startup) never pays for three SDKs, and so a missing optional SDK only
breaks the provider that needs it.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from .base import (
    CloudPlannerError,
    CloudProvider,
    PlanAttempt,
    ProviderSpec,
    sanitize,
)

_MODULES: dict[CloudProvider, str] = {
    CloudProvider.OPENAI: "openai_provider",
    CloudProvider.ANTHROPIC: "anthropic_provider",
    CloudProvider.GEMINI: "gemini_provider",
}

_LABELS: dict[CloudProvider, str] = {
    CloudProvider.OPENAI: "OpenAI",
    CloudProvider.ANTHROPIC: "Anthropic (Claude)",
    CloudProvider.GEMINI: "Google (Gemini)",
}


def get_adapter(provider: CloudProvider) -> ModuleType:
    return importlib.import_module(f".{_MODULES[provider]}", __name__)


def label(provider: CloudProvider) -> str:
    return _LABELS[provider]


def spec(provider: CloudProvider) -> ProviderSpec:
    adapter = get_adapter(provider)
    return ProviderSpec(
        provider=provider,
        label=_LABELS[provider],
        model_hint=adapter.MODEL_HINT,
        key_hint=adapter.KEY_HINT,
    )


def all_providers() -> list[CloudProvider]:
    return list(_MODULES)


__all__ = [
    "CloudPlannerError",
    "CloudProvider",
    "PlanAttempt",
    "ProviderSpec",
    "all_providers",
    "get_adapter",
    "label",
    "sanitize",
    "spec",
]
