# 07 — Tracing tab realtime

**What to build:** TUI Tracing tab rendering the live trace projection.

**Blocked by:** 03 — Trace subtypes + persistence.

**Status:** ready-for-agent

- [ ] Tab subscribes to `Session.append`, shows `router.decision/kb.hit/ocr.page` spans live
- [ ] Works on resumed sessions
