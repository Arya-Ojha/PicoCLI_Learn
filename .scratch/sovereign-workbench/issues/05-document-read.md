# 05 — NuExtract document read

**What to build:** VLM-only page pipeline producing Markdown + structured findings with page refs.

**Blocked by:** 01 — Cwd-jail hardening, 03 — Trace subtypes + persistence.

**Status:** ready-for-agent

- [ ] `ocr.read` renders pages to PNG at DPI 200, NuExtract-3 4B converts to Markdown + JSON
- [ ] Per-page `ocr.page{png, text}` kept in trace, rolling fuse for long PDFs
- [ ] Local VLM + OpenRouter vision alias for routing tests
