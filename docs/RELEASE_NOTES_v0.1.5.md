# Needle Factory Sim v0.1.5

A second hardening pass. Two more adversarial reviews covered the areas the
first one didn't — game rules against the spec, malformed model output, and the
packaging excludes — and everything they found is fixed and pinned by tests.
Test count 79 → 104.

## The AI can no longer talk the factory into a wrong-but-legal action

Pydantic was validating AI arguments in lax mode, so it **rewrote** malformed
values instead of rejecting them:

| Model produced | Was silently executed as | Now |
|---|---|---|
| `target_c: true` | `1 °C` (deep cold, cargo damage) | escalates to CLOUD |
| `target_c: "30"` | `30` | escalates to CLOUD |
| `open: "yes"` | `True` | escalates to CLOUD |
| `wait: {seconds: true}` | `1` | plan validation fails |

All argument models are now `strict=True`. This is the safety-relevant fix in
this release: a garbage tool call must reach the Cloud planner or be rejected —
never be reshaped into something the controller will happily accept. The same
strictness now applies to Cloud ExecutionPlans.

Related: an unusable confidence no longer passes the routing gate. `NaN` failed
every comparison (so `confidence < threshold` was `False` and it routed LOCAL);
values outside 0..1 were never range-checked. Both now become "unusable" and
route to CLOUD.

## Status no longer lies about how a run ended

- **Emergency Stop used to erase a GAME OVER.** After the cargo was destroyed,
  pressing E-STOP flipped the status to "EMERGENCY STOPPED" while HP still read
  0, and every later rejection blamed the wrong cause. E-Stop is now refused
  once the run is already over, keeping the real reason visible.
- **A won mission could be un-won.** `MISSION_SUCCESS` was recomputed on every
  move, so leaving the goal sector silently discarded the win — and setting the
  goal sector to 60 °C afterwards killed the cargo while the pill still read
  "MISSION SUCCESS 🎉". Mission success is now terminal, and time stops when a
  run ends (temperatures also no longer drift after GAME OVER).

## The UI can no longer get stuck waiting for a result

An oversized JSON number in a Needle response raised `OverflowError` inside the
response parser, and `agent.reset()` sat outside the crash guard. Either way the
worker slot died without emitting a result, leaving the input box, Execute and
all demo buttons disabled on "Needle thinking…" until Reset. Both are inside the
guard now, and both worker slots always emit a result even on an unexpected error.

## Shutdown no longer aborts the process

The **Test connection** button added in v0.1.4 introduced a crash: closing Cloud
Settings while the check was in flight destroyed a running `QThread` and aborted
the process (reproduced: exit code 9). Uninterruptible worker threads are now
handed to a single `thread_guard`, and the app's exit path leaves via `os._exit`
if one is still stuck — verified to exit 0 in the same scenario. (v0.1.4's
partial fix did not survive interpreter teardown.)

## Smaller fixes

- The cargo HP bar showed "HP 0 / 100" while the cargo was still alive (and hid
  the first 40 ms of damage) — it now rounds up while alive.
- `set_temperature` rejects fractional targets, matching the spec's `int`.

## Verified, not changed

The PyInstaller excludes were audited by blocking every excluded module at import
time and running the real inference path, then by inspecting the shipped build:
no `numpy`/`jax`/`flax`/`scipy` in the bundle, all 146 `huggingface_hub`
submodules present, and the real engine download path completes. The first-run
provisioning in the frozen app is safe.

## Tests

104 automated tests on Ubuntu and Windows via CI. New: strict-argument
regressions, confidence hygiene, worker crash-safety, terminal-state rules, and
the dialog thread handover. Real-model checks re-run after the changes — Demo
A/B/C routing unchanged, paraphrase robustness still 20/25.

## Windows installer

`NeedleFactorySim-Setup-0.1.5.exe` — per-user install, no admin rights, not
code-signed (SmartScreen: *More info → Run anyway*).

## Known limitations

- An abandoned cloud request (after Reset / E-Stop) cannot be cancelled
  mid-flight; a following request queues behind it for up to the 20 s timeout.
- Needle 2's base model is unstable on Korean prompts; demo presets use English.
- Live cloud planning still needs your own API key and model ID. If the API
  rejects the strict schema, the monitor will say the plan came from the
  JSON-mode fallback.
