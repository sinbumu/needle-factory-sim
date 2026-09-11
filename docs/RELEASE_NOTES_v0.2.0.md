# Needle Factory Sim v0.2.0

The Cloud planner is no longer OpenAI-only: **Anthropic (Claude)** and
**Google (Gemini)** are now first-class providers alongside it.

## Multi-provider Cloud Settings

Cloud Settings gains a **Provider** dropdown — OpenAI, Anthropic (Claude),
Google (Gemini). Each provider keeps its **own key and model slot**, so
switching the dropdown never discards what you already typed and you can keep
all three configured in one session, switching planners between runs.

Everything that made the OpenAI path safe applies to all three:

- Keys live **only in process memory** — never written to disk, env vars, logs
  or the monitor, and gone when the app exits. Errors are redacted.
- **Test connection** works per provider: it resolves the model id, so it
  verifies the key and the model without spending tokens.
- Model IDs stay **user-supplied** — the field only hints at a valid one
  (`gpt-4.1`, `claude-opus-5`, `gemini-2.5-pro`); nothing is hardcoded.
- The AI Monitor shows which provider produced a plan and whether it came from
  the structured-output path or that provider's JSON fallback.

## How each provider is asked for a plan

All three receive the identical system contract and factory snapshot, return an
`ExecutionPlan` and execute nothing. Only the transport differs:

| Provider | Structured output | Fallback |
|---|---|---|
| OpenAI | `chat.completions.parse(response_format=ExecutionPlan)` | JSON mode + strict validation |
| Anthropic | `messages.parse(output_format=ExecutionPlan)` | JSON in the prompt (code fences tolerated) |
| Gemini | `response_schema=ExecutionPlan` + JSON mime type | schema in the prompt |

A fallback runs **only** when the structured path is genuinely unsupported — a
400 from the provider. An auth, quota or network failure surfaces immediately
instead of burning a second round trip, and is classified per provider
(`AUTHENTICATION_ERROR`, `RATE_LIMIT`, `UNSUPPORTED_MODEL`, …).

Provider SDKs are imported lazily, so startup cost is unchanged and a provider
whose SDK is missing reports `PROVIDER_UNAVAILABLE` rather than crashing.

## Tests

124 automated tests (was 105) on Ubuntu and Windows. New: the Anthropic and
Gemini adapters against fake clients — request shape (schema, system prompt,
timeout units — Anthropic takes seconds, Gemini milliseconds), structured-output
first, fallback only on a 400, strict plan validation, no key in any error — plus
the dialog's per-provider credential handling.

The packaging excludes were re-audited against the new SDKs by blocking every
excluded module at import time; the shipped bundle carries anthropic, openai and
google.genai with still no numpy/jax/scipy.

## Windows installer

`NeedleFactorySim-Setup-0.2.0.exe` — per-user install, no admin rights, not
code-signed (SmartScreen: *More info → Run anyway*). 54 MB (up from 48 MB with
the two extra SDKs).

## Known limitations

- No provider's structured-output path has been exercised against a live API
  yet. If one rejects the strict plan schema, that provider's JSON fallback
  handles the request and the monitor says so.
- An abandoned cloud request (after Reset / E-Stop) cannot be cancelled
  mid-flight; a following request queues behind it for up to the 20 s timeout.
- Needle 2's base model is unstable on Korean prompts; demo presets use English.
