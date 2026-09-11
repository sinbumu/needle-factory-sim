"""Cloud planner providers.

Adapter modules are imported lazily so launching the app (and the frozen
build's startup) never pays for three SDKs, and so a missing optional SDK only
breaks the provider that needs it.

The imports in `get_adapter` are written out one per provider rather than
resolved from a name: a computed `importlib.import_module()` is invisible to
PyInstaller's static analysis, which silently left every adapter out of the
packaged build and made each button that touches a provider look dead.
"""

from __future__ import annotations

from types import ModuleType

from .base import (
    CloudPlannerError,
    CloudProvider,
    PlanAttempt,
    ProviderSpec,
    sanitize,
)

_LABELS: dict[CloudProvider, str] = {
    CloudProvider.OPENAI: "OpenAI",
    CloudProvider.ANTHROPIC: "Anthropic (Claude)",
    CloudProvider.GEMINI: "Google (Gemini)",
}


def get_adapter(provider: CloudProvider) -> ModuleType:
    if provider is CloudProvider.OPENAI:
        from . import openai_provider as adapter
    elif provider is CloudProvider.ANTHROPIC:
        from . import anthropic_provider as adapter
    elif provider is CloudProvider.GEMINI:
        from . import gemini_provider as adapter
    else:  # pragma: no cover - CloudProvider is exhaustive
        raise ValueError(f"unknown provider: {provider!r}")
    return adapter


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
    return list(_LABELS)


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
