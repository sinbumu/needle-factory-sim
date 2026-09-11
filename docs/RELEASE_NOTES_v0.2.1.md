# Needle Factory Sim v0.2.1

**Fixes a broken v0.2.0 installer — use this build instead.**

## What was wrong

In the packaged v0.2.0 app, every button in the top bar (Reset, the Demo
presets, Execute, Cloud Settings) did nothing at all. Running from source was
fine; only the installer build was affected.

The provider registry added in v0.2.0 loaded its adapters by a **computed**
module name:

```python
importlib.import_module(f".{_MODULES[provider]}", __name__)
```

PyInstaller resolves imports statically, so it could not see those names and
left `openai_provider`, `anthropic_provider` and `gemini_provider` out of the
bundle entirely. Every handler that resolves the active provider's label then
raised `ModuleNotFoundError`, and because the packaged app has no console the
exception was invisible — the button simply appeared dead.

The registry now imports each adapter with an ordinary `from . import …`
statement, one per provider. Laziness is unchanged (the heavy SDKs are still
imported only when a provider is actually used), but the imports are now
visible to the packager.

## Why it shipped, and what stops it next time

The v0.2.0 verification launched the packaged app and took a screenshot — it
never *used* anything, so a dead button looked identical to a working one.

The packaged app now has a self-check, and the installer build runs it as a
gate:

```text
NeedleFactorySim.exe --selfcheck <report.txt>
```

It loads all three provider adapters and drives the real top-bar handlers
(reset, demo preset, tutorial open/close, emergency stop) off-screen, writing
the outcome to a file since the packaged app has no console. If anything fails,
`scripts/build_installer.ps1` aborts and no installer is produced. Verified
against the installed build:

```text
frozen: True
openai / anthropic / gemini: adapter OK
handler reset / demo A / tutorial open / tutorial close / emergency stop: OK
RESULT: OK
```

## Everything else

Unchanged from v0.2.0: the multi-provider Cloud planner (OpenAI, Anthropic
Claude, Google Gemini) with per-provider key/model slots, memory-only keys,
per-provider Test connection, and 124 automated tests on Ubuntu and Windows.
