# Needle Factory Sim v0.2.2

Fixes two bugs in the Gemini provider, both found while testing against a live
Google API key. Gemini planning now works end to end.

## Test connection returned a bare UNKNOWN_ERROR

`test_connection` called the SDK off a temporary:

```python
_client(api_key, timeout_s).models.get(model=model_id)
```

`genai.Client` closes its underlying HTTP transport when it is garbage
collected, and the client here was collected the moment its `models` attribute
was read — so the request failed with `Cannot send a request, as the client has
been closed` before it was ever sent, which the classifier could only report as
`UNKNOWN_ERROR`. The client is now held for the whole call, in all three
providers. A regression test reproduces the collection (and was checked to fail
against the old code).

## Gemini planning reported PLAN_VALIDATION_FAILED and never fell back

google-genai converts a Pydantic `response_schema` into its own `Schema` type,
which rejects the `discriminator` key our tagged union emits. That raised a
`ValidationError` **before anything was sent**, and the adapter mistook it for
"the model returned a bad plan": it reported `PLAN_VALIDATION_FAILED` and
skipped the fallback that would have worked.

A schema the provider cannot take is now distinguished from a plan the model
got wrong. The first routes to the prompt-schema request; only a real reply
that fails validation is reported as `PLAN_VALIDATION_FAILED`.

Gemini therefore always shows "(JSON fallback)" in the monitor — expected for
this provider, not a fault. Its alternative `response_json_schema` mode was
measured too: the API accepts it but does not enforce the union, returning
steps carrying another action's arguments, so it is not used.

## Verified live

With a real key, `gemini-2.5-flash` produced exactly the intended Demo C plan:

```text
1. set_temperature(A, 30)   2. set_temperature(B, 30)   3. wait(2)
4. toggle_door(B, open)     5. move_robot(A)            6. move_robot(B)
7. move_robot(E)
```

Note: some newer preview models (e.g. `gemini-3.8-flash`) are heavily loaded and
answer `503 high demand` or `504 deadline exceeded`. That is the provider, not
the app — the monitor reports `SERVER_ERROR` and the command can be run again.
The app does not retry on its own, so an abandoned request stays bounded by the
20 s timeout.

## Tests

129 (was 124), including the client-lifetime regression for all three providers
and both sides of the Gemini schema/plan distinction.
