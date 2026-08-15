# 05 — Compaction (auto + manual)

**What to build:** auto-compaction at the token threshold (`contextTokens > window − reserve`) and manual `/compact [instructions]`, summarising old turns into a compaction-summary node.

**Blocked by:** 02 — Tracer bullet: headless text response.

**Status:** ready-for-agent

- [ ] Auto-compaction fires when context tokens exceed window − reserve (reserve default 16384).
- [ ] Compaction summarises old turns into a compaction-summary node and keeps the system prompt + recent window.
- [ ] Manual `/compact [instructions]` triggers compaction with steering instructions.
