# Trace as a session projection with subtypes

LangGraph-style tracing must persist per session, resume on reopen, and render realtime in a Tracing tab without a second source of truth. We decided the trace is a live projection over the existing append-only `Node` tree, with new events (`router.decision`, `kb.hit`, `ocr.page`) recorded as `tool_request` subtypes in the same JSONL, so resume is `Session.load`.
