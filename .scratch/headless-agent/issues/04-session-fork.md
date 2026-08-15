# 04 — Session fork & branch-scoped context

**What to build:** rewind to an earlier node and fork a new branch; only the active branch is sent to the model.

**Blocked by:** 02 — Tracer bullet: headless text response.

**Status:** ready-for-agent

- [ ] A session can fork from an earlier node, creating a new branch.
- [ ] Only the active branch's nodes are assembled into the model context; abandoned branches are excluded.
- [ ] Forking is append-only: existing nodes are never edited or deleted.
