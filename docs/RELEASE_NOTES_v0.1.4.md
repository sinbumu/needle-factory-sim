# Needle Factory Sim v0.1.4

A hardening release: an adversarial review of the runtime found several real
defects, all fixed and pinned with regression tests. Test count went 42 → 79 and
CI now runs them on every push.

## Safety fixes

- **The tutorial overlay could hide a dying cargo.** The overlay covers the whole
  window and swallowed clicks, so Emergency Stop was unclickable while the
  simulation kept running — the cargo could be destroyed with no way to stop it.
  The tour now **pauses the simulation** while it is open (and is unavailable
  while an inference or plan is in flight).
- **A worker thread touched the UI.** The Needle `engine_error` handler was a
  lambda, which Qt resolved to a direct connection — so the log widget was
  written from the Needle thread on exactly the path users hit most (first-run
  engine provisioning failure). Now a bound slot, delivered queued to the GUI thread.
- **GAME_OVER did not stop a running plan.** A plan could sit in a `wait` for up
  to 10 s after the cargo was already destroyed, then report that wait as
  SUCCEEDED. Plans now abort as soon as the factory is inoperable
  (game over or emergency stop), and the aborted step is reported as FAILED.
- **Cancel mislabelled completed work.** Pressing Emergency Stop or Reset within
  the 400 ms pacing delay after a step landed marked that step CANCELLED, even
  though the controller had applied it and nothing is ever rolled back. Only
  in-progress steps become CANCELLED now.
- **A clock jump could kill the cargo instantly.** `time.monotonic()` includes
  system suspend on Windows, so one tick after a laptop resume applied hours of
  damage in a single frame. Tick deltas are now clamped.
- **Shutdown could abort the process.** Closing the app while Needle or a cloud
  call was still running risked destroying a live `QThread`. Busy threads are
  now detached and outlive the window instead.
- Keyboard focus can no longer Tab out of the tutorial onto the controls behind it.
- Reset now clears the previous run's routing verdict, plan and step table, which
  otherwise looked like a plan still pending against a fresh factory.

## New

- **MIT license** and a **GitHub Actions CI** workflow (Ubuntu + Windows).
- **Test connection** button in Cloud Settings — verifies the key and model ID
  without spending tokens, and reports errors with the key redacted.
- **Command history**: ↑ / ↓ recalls previously executed commands.
- The app version is shown in the title bar and header; the event log is timestamped.
- The monitor now says when a cloud plan came from the JSON-mode fallback instead
  of structured outputs, so a silently degraded path is visible.

## Tests

79 automated tests (was 42), covering the controller rules, confidence routing,
strict plan validation, **the plan executor** (sequencing, wait, cancellation,
failure policy, live re-validation), **the cloud planner** (context building,
structured-output handling, error classification, API-key redaction) and the
new UI widgets. Plus `scripts/safety_check.py` for window-level checks and the
existing spike/smoke scripts for the real model.

## Windows installer

`NeedleFactorySim-Setup-0.1.4.exe` — per-user install, no admin rights,
not code-signed (SmartScreen: *More info → Run anyway*). The Needle engine and
model download on first launch; local inference is offline afterwards.

## Known limitations

- An abandoned cloud request (after Reset / E-Stop) cannot be cancelled mid-flight;
  a following request queues behind it for up to the 20 s timeout.
- Needle 2's base model is unstable on Korean prompts; demo presets use English.
- Live cloud planning still needs your own API key and model ID.
