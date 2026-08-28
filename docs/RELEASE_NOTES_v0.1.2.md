# Needle Factory Sim v0.1.2

Adds a **Windows installer** on top of v0.1.1 (dark-themed dashboard + full
Edge-AI hybrid control PoC).

## Windows installer

- `NeedleFactorySim-Setup-0.1.2.exe` — per-user install, no admin rights needed,
  Start Menu entry + optional desktop icon, clean uninstaller.
- **Not code-signed**: Windows SmartScreen will warn about an unknown publisher —
  choose *More info → Run anyway*.
- The Needle engine/model are **not** bundled. The app downloads them to
  `~/.cache/cactus-needle` on first launch (internet needed once); afterwards
  local inference runs fully offline. Verified on a clean-cache environment.
- Built with PyInstaller (onedir, training-stack excluded) + Inno Setup 6.
  Rebuild locally with `scripts/build_installer.ps1`.

## What this demo shows

Explicit natural-language commands are handled by a 14MB **Needle 2 local SLM**
(on-device tool-call candidates with calibrated confidence); goal-oriented
requests escalate to a **Cloud LLM planner** (OpenAI) that sees the full factory
snapshot and returns a strict structured ExecutionPlan. Either way, a
**deterministic FactoryController** is the only thing that can change factory
state — every step is re-validated against live physics rules at execution time.

- AUTO routing: confidence ≥ 0.75 + exactly one schema-valid call → LOCAL,
  anything else → CLOUD (FORCE LOCAL / FORCE CLOUD overrides shown honestly)
- Strict Pydantic ExecutionPlan (≤8 steps, bounded `wait`), cancellable
  step-by-step executor, session-only in-memory API key
- Demo A (local control) / Demo B (safety rejection) / Demo C (cloud planning)

## How to run from source

```bash
uv sync
uv run python -m needle_factory_sim
```

or `run.bat`. Cloud planning requires your own OpenAI API key + model ID via
Cloud Settings.

## Known limitations

- Unsigned installer (SmartScreen warning)
- Needle 2 base model is unstable on Korean prompts; demo presets use English
- Live cloud path verified with fixture plans and schema tests; needs a
  user-provided key for live calls
