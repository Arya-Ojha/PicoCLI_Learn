# 01 — Cwd-jail hardening

**What to build:** the opened folder becomes the jail — escapes rejected, bash cwd-locked with timeout and no network binaries, denials traced.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Absolute/`..`/symlink escapes outside cwd return `is_error`
- [ ] `bash` cwd-locked, 30s timeout, `curl/wget/ssh` denied
- [ ] Tests for jail escapes + bash jail in `tests/test_tools.py`
