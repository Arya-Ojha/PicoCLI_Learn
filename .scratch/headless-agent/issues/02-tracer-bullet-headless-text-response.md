# 02 — Tracer bullet: headless text response

**What to build:** `pico run "…"` returns a text response and persists an append-only session (user node + assistant node) to disk, driven by a minimal FSM (`idle → streaming → done`). No tools yet.

**Blocked by:** 01 — Unified AI call + OpenRouter client.

**Status:** ready-for-agent

- [ ] `pico run "hello"` prints the model's text response.
- [ ] A session is persisted as JSONL with a user node and an assistant node, each with id/parent_id/timestamp/payload.
- [ ] The FSM transitions idle → streaming → done for a simple prompt.
- [ ] A scripted fake provider drives the loop deterministically in tests (no network).
