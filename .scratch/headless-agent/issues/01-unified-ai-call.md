# 01 — Unified AI call + OpenRouter client

**What to build:** a streaming, async, provider-agnostic "AI call" in `pico_ai`. Given a prompt (and optional tool definitions), it sends a request to OpenRouter and returns a normalized stream of text / thinking / tool-call blocks plus usage. The API key comes from the environment; the model is configurable with a default.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A unified request/response type exists that is provider-agnostic (no OpenRouter-specific fields leak into callers).
- [ ] An async, streaming client sends a prompt to OpenRouter and yields normalized blocks (text, thinking, tool-call) as they arrive.
- [ ] The response includes usage (input/output tokens) when the provider reports it.
- [ ] Tool definitions round-trip: a caller can pass tool schemas and receive tool-call blocks with name + arguments.
- [ ] A fake transport lets tests exercise the client with no network.
