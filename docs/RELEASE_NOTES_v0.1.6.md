# Needle Factory Sim v0.1.6

A follow-up to v0.1.5's hardening pass, so the installer matches `main`.

## Fix

Making `MISSION_SUCCESS` terminal in v0.1.5 had a side effect: if a Cloud plan
contained a step after the one that reaches the goal, that trailing step was
rejected with `MISSION_COMPLETE` and the whole plan was reported **FAILED** —
even though the cargo had arrived safely. Reaching the goal now completes the
plan as **SUCCEEDED** and marks the remaining steps SKIPPED.

This only shows up when the planner adds a redundant trailing action, which is
exactly the kind of thing a live model does, so it is worth having in the
installer before live Cloud testing.

## Everything else

Unchanged from [v0.1.5](https://github.com/sinbumu/needle-factory-sim/releases/tag/v0.1.5):
strict AI-argument validation, terminal-state correctness, crash-safe workers,
MIT license and CI. 105 automated tests (was 104) on Ubuntu and Windows.

Documentation now also records that the OpenAI structured-output path has not
been exercised against the live API — if it rejects the strict plan schema, the
JSON-mode fallback handles the request and the monitor says so.

## Windows installer

`NeedleFactorySim-Setup-0.1.6.exe` — per-user install, no admin rights, not
code-signed (SmartScreen: *More info → Run anyway*). The Needle engine and model
download on first launch; local inference is offline afterwards.
