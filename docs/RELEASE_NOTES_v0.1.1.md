# Needle Factory Sim v0.1.1

First public release (v0.1.0 tag marks the pre-UI-polish snapshot; this release
adds the dark-themed dashboard on top of it).

## What this demo shows

Explicit natural-language commands are handled by a 14MB **Needle 2 local SLM**
(on-device tool-call candidates with calibrated confidence); goal-oriented
requests escalate to a **Cloud LLM planner** (OpenAI) that sees the full factory
snapshot and returns a strict structured ExecutionPlan. Either way, a
**deterministic FactoryController** is the only thing that can change factory
state — every step is re-validated against live physics rules at execution time.

## Local Needle routing

- `agent.reset()` + exactly one `agent.complete()` per command (no agentic loop)
- 5 constrained tools (`Literal` / `Field` grammar limits)
- AUTO routing: confidence ≥ 0.75 + exactly one schema-valid call → LOCAL;
  anything else → CLOUD. FORCE LOCAL / FORCE CLOUD overrides (with visible
  `OVERRIDE = TRUE`).
- Measured on-device: ~0.1 s latency, ~350 tok/s decode, ~55 MB peak RAM.

## Cloud planning

- Full state snapshot + explicit rules context; the cloud never executes tools
- Strict Pydantic ExecutionPlan (≤8 steps, `wait` ≤10 s each / ≤15 s total,
  contiguous order, extra fields forbidden)
- Cancellable step-by-step PlanExecutor; simulation keeps running during `wait`
- Session-only in-memory API key (never stored, never logged)

## Safety Controller

Adjacency, temperature safety, door state, contamination/reset rules, cargo HP,
emergency stop, stale-response protection by request id. Rejected actions change
nothing.

## UI

Dark-themed PySide6 dashboard: temperature-gradient sector cards with kind icons
and band chips, robot location highlight, door/contamination badges, cargo HP
bar colored by health, mission status pill, and an AI monitor with colored
routing / controller verdicts / plan-step statuses.

## Demo A/B/C

- **A** — "Set sector A temperature to 30 degrees." → LOCAL (confidence 0.84) → accepted, gradual transition
- **B** — "Move the robot directly to sector E." → valid tool call (0.95) → controller rejects `NOT_ADJACENT`
- **C** — goal-oriented transport → Needle yields no call → CLOUD plan → validated, step-wise execution to mission success

## How to run

```bash
uv sync
uv run python -m needle_factory_sim
```

or `run.bat` on Windows. First launch downloads the local Needle engine (internet
once); local inference is offline afterwards. Cloud planning requires your own
OpenAI API key + model ID via Cloud Settings.

## Known limitations

- Needle 2 base model is unstable on Korean prompts (measured 0.00–0.21
  confidence); demo presets use English fallback prompts
- Live cloud path verified with fixture plans and schema tests; not exercised
  against the live OpenAI API in the build environment (no key)
- Single plan at a time; no rollback of succeeded steps (honest failure reporting)
