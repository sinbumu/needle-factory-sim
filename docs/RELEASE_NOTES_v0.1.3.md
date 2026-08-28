# Needle Factory Sim v0.1.3

## New in this release

- **First-launch tutorial** — a guided coach-mark tour that dims the window and
  walks through every control step by step (factory map, command input, demo
  presets, Execute, routing mode, Cloud Settings, AI monitor, safety-controller
  verdict, Emergency Stop, Reset). It appears automatically only on the very
  first launch; reopen it anytime with the **❓ Tutorial** button in the top bar.
- **Layout** — the deterministic controller verdict and the event log moved to
  the left column under the mission status, visible without scrolling.
- **Paraphrase robustness** — Needle tool descriptions now carry synonym hints
  ("go/head/drive", "warm up/cool down", "clean/decontaminate",
  "stop everything/halt/abort"…). Measured on 25 paraphrased commands:
  14/25 → **20/25 executed locally, zero wrong actions** — every miss escalates
  safely to the Cloud route. Demo A/B/C routing re-verified unchanged.
  See the README's paraphrase section for the method.

## Windows installer

- `NeedleFactorySim-Setup-0.1.3.exe` — per-user install (no admin rights),
  Start Menu entry, optional desktop icon, clean uninstaller. Upgrades a
  previous install in place.
- **Not code-signed**: Windows SmartScreen will warn — *More info → Run anyway*.
- Needle engine/model are downloaded on first launch (internet once), then
  local inference runs fully offline.

## What this demo shows

A 14MB **Needle 2 local SLM** turns explicit commands into tool-call candidates
with calibrated confidence; goal-oriented requests escalate to a **Cloud LLM
planner** (OpenAI, strict structured ExecutionPlan); and a **deterministic
FactoryController** re-validates every action against live physics rules —
neither AI can change factory state directly.

## Run from source

```bash
uv sync
uv run python -m needle_factory_sim
```

## Known limitations

- Unsigned installer (SmartScreen warning)
- Needle 2 base model is unstable on Korean prompts; demo presets use English
- Some paraphrases still route to CLOUD by design (safe escalation over
  wrong execution)
