# 04 — Local Corpus search with hard citations

**What to build:** folder-mounted corpus with local search returning cited spans or "not in corpus".

**Blocked by:** 01 — Cwd-jail hardening, 03 — Trace subtypes + persistence.

**Status:** ready-for-agent

- [ ] `~/pico-kb/` mount, 512/100 chunking, CPU search + file ACL at query
- [ ] `kb.search` returns `doc/chunk/page` spans, traced as `kb.hit`
- [ ] Missing coverage answers "not in corpus"
