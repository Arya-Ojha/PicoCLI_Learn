# 02 — Capability Router + Registry

**What to build:** deterministic `models.yaml` registry mapping capability labels to models, with testing-only flag and logged decisions.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `~/.pico/models.yaml` with `id, provider, ctx, vram_gb, caps[]`, `testing_only`
- [ ] `route(capability) -> model-id` with fallback + `router.decision` reason
- [ ] `Settings.model=""` means router decides; explicit id pins
