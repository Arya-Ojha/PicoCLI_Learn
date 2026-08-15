# 06 — Extension binding & plugin loading

**What to build:** `register_tool`, `register_provider`, and lifecycle hooks (`on_session_start`, `tool.before.*`, `tool.after.*`); plugins load from a directory and via explicit registration.

**Blocked by:** 03 — Tools: read / write / edit / bash.

**Status:** ready-for-agent

- [ ] A plugin can register a custom tool that the agent can invoke.
- [ ] A plugin can register a custom provider.
- [ ] Lifecycle hooks fire: on_session_start, tool.before.*, tool.after.*.
- [ ] Plugins load from a plugins directory and via explicit registration.
