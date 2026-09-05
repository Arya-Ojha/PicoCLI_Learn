# 03 — Trace subtypes + persistence

**What to build:** LangGraph-style trace as a live projection over session nodes, persisted and resumable.

**Blocked by:** 01 — Cwd-jail hardening.

**Status:** ready-for-agent

- [ ] `router.decision`, `kb.hit`, `ocr.page` as `tool_request` subtypes in same JSONL
- [ ] Resume via `Session.load` restores full trace
- [ ] Tests for subtype round-trip save/load
